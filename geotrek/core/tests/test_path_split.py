# -*- coding: utf-8 -*-
from django.test import TransactionTestCase
from django.contrib.gis.geos import LineString, Point
from django.conf import settings

from geotrek.common.utils import almostequal

from geotrek.core.factories import PathFactory, TopologyFactory, NetworkFactory, UsageFactory
from geotrek.core.models import Path, Topology


class SplitPathTest(TransactionTestCase):
    def test_split_attributes(self):
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        ab.networks.add(NetworkFactory.create())
        ab.usages.add(UsageFactory.create())
        PathFactory.create(geom=LineString((2, 0), (2, 2)))
        ab_2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        self.assertEqual(ab.datasource, ab_2.datasource)
        self.assertEqual(ab.stake, ab_2.stake)
        self.assertListEqual(list(ab.networks.all()), list(ab_2.networks.all()))
        self.assertListEqual(list(ab.usages.all()), list(ab_2.usages.all()))

    def test_split_tee_1(self):
        """
               C
        A +----+----+ B
               |
               +      AB exists. Add CD.
               D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        self.assertEqual(ab.length, 4)
        cd = PathFactory.create(geom=LineString((2, 0), (2, 2)))
        self.assertEqual(cd.length, 2)

        # Make sure AB was split :
        ab.reload()
        self.assertEqual(ab.geom, LineString((0, 0), (2, 0)))
        self.assertEqual(ab.length, 2)  # Length was also updated
        # And a clone of AB was created
        clones = Path.objects.filter(name="AB").exclude(pk=ab.pk)
        self.assertEqual(len(clones), 1)
        ab_2 = clones[0]
        self.assertEqual(ab_2.geom, LineString((2, 0), (4, 0)))
        self.assertEqual(ab_2.length, 2)  # Length was also updated

    def test_split_tee_2(self):
        """
        CD exists. Add AB.
        """
        cd = PathFactory.create(geom=LineString((2, 0), (2, 2)))
        self.assertEqual(cd.length, 2)
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))

        # Make sure AB was split :
        self.assertEqual(ab.geom, LineString((0, 0), (2, 0)))
        self.assertEqual(ab.length, 2)  # Length was also updated

        clones = Path.objects.filter(name="AB").exclude(pk=ab.pk)
        ab_2 = clones[0]
        self.assertEqual(ab_2.geom, LineString((2, 0), (4, 0)))
        self.assertEqual(ab_2.length, 2)  # Length was also updated

    def test_split_cross(self):
        """
               C
               +
               |
        A +----+----+ B
               |
               +      AB exists. Add CD.
               D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((2, -2), (2, 2)))
        ab.reload()
        ab_2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        cd_2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(ab.geom, LineString((0, 0), (2, 0)))
        self.assertEqual(cd.geom, LineString((2, -2), (2, 0)))
        self.assertEqual(ab_2.geom, LineString((2, 0), (4, 0)))
        self.assertEqual(cd_2.geom, LineString((2, 0), (2, 2)))

    def test_split_cross_on_deleted(self):
        """
        Paths should not be splitted if they cross deleted paths.
        (attribute delete=True)
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        self.assertEqual(len(Path.objects.all()), 1)
        ab.delete()
        self.assertEqual(len(Path.objects.all()), 0)
        cd = PathFactory.create(name="CD", geom=LineString((2, -2), (2, 2)))
        self.assertEqual(len(Path.objects.all()), 1)

    def test_split_on_update(self):
        """
                                       + E
                                       :
        A +----+----+ B         A +----+----+ B
                                       :
        C +----+ D              C +----+ D

                                    AB and CD exist. CD updated into CE.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, -2), (2, -2)))
        self.assertEqual(ab.length, 4)
        self.assertEqual(cd.length, 2)

        cd.geom = LineString((0, -2), (2, -2), (2, 2))
        cd.save()
        ab.reload()
        self.assertEqual(ab.length, 2)
        self.assertEqual(cd.length, 4)
        ab_2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        cd_2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(ab_2.length, 2)
        self.assertEqual(cd_2.length, 2)

    def test_split_twice(self):
        """

             C   D
             +   +
             |   |
        A +--+---+--+ B
             |   |
             +---+

        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((1, 2), (1, -2),
                                                           (3, -2), (3, 2)))
        ab.reload()
        self.assertEqual(ab.length, 1)
        self.assertEqual(cd.length, 2)
        ab_clones = Path.objects.filter(name="AB").exclude(pk=ab.pk)
        cd_clones = Path.objects.filter(name="CD").exclude(pk=cd.pk)
        self.assertEqual(len(ab_clones), 2)
        self.assertEqual(len(cd_clones), 2)
        self.assertEqual(ab_clones[0].geom, LineString((1, 0), (3, 0)))
        self.assertEqual(ab_clones[1].geom, LineString((3, 0), (4, 0)))

        self.assertEqual(cd_clones[0].geom, LineString((1, 0), (1, -2),
                                                       (3, -2), (3, 0)))
        self.assertEqual(cd_clones[1].geom, LineString((3, 0), (3, 2)))

    def test_add_shortest_path(self):
        """
        A +----         -----+ C
               \       /
                \     /
                 --+--
                   B

               D        E
        A +---+---------+---+ C
               \       /
                \     /
                 --+--
                   B
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0),
                                                           (6, -2), (8, -2)))
        cb = PathFactory.create(name="CB", geom=LineString((14, 0), (12, 0),
                                                           (10, -2), (8, -2)))
        de = PathFactory.create(name="DE", geom=LineString((4, 0), (12, 0)))

        # Paths were split, there are 5 now
        self.assertEqual(len(Path.objects.all()), 5)

        ab.reload()
        cb.reload()
        de.reload()
        ab_2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        cb_2 = Path.objects.filter(name="CB").exclude(pk=cb.pk)[0]

        self.assertEqual(de.geom, LineString((4, 0), (12, 0)))
        self.assertEqual(ab.geom, LineString((0, 0), (4, 0)))
        self.assertEqual(ab_2.geom, LineString((4, 0), (6, -2), (8, -2)))
        self.assertEqual(cb.geom, LineString((14, 0), (12, 0)))
        self.assertEqual(cb_2.geom, LineString((12, 0), (10, -2), (8, -2)))

    def test_split_almost(self):
        """

           C   D
           +   +
            \ /
        A +--V--+ B
             E
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((1, 1), (2, -0.2),
                                                           (3, 1)))
        ab.reload()
        cd.reload()
        eb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        ed = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(ab.geom, LineString((0, 0), (2, -0.2)))
        self.assertEqual(cd.geom, LineString((1, 1), (2, -0.2)))
        self.assertEqual(eb.geom, LineString((2, -0.2), (4, 0)))
        self.assertEqual(ed.geom, LineString((2, -0.2), (3, 1)))

    def test_split_almost_2(self):
        """
           + C
           |
        A +------- ... ----+ B
           |
           + D
        """
        cd = PathFactory.create(name="CD", geom=LineString((0.1, 1), (0.1, -1)))
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (10000000, 0)))
        ab.reload()
        cd.reload()
        self.assertEqual(ab.geom, LineString((0.1, 0), (10000000, 0)))
        self.assertEqual(cd.geom, LineString((0.1, 1), (0.1, 0)))
        self.assertEqual(len(Path.objects.all()), 3)

    def test_split_almost_3(self):
        """
            + C
            |
        A +-+------ ... ----+ B
            |
            + D
        """
        cd = PathFactory.create(name="CD", geom=LineString((1.1, 1), (1.1, -1)))
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (10000000, 0)))
        ab.reload()
        cd.reload()
        self.assertEqual(ab.geom, LineString((0, 0), (1.1, 0)))
        self.assertEqual(cd.geom, LineString((1.1, 1), (1.1, 0)))
        self.assertEqual(len(Path.objects.all()), 4)

    def test_split_almost_4(self):
        """
                 C
            -----+----+ A
            |    |
            |    |
            -----+----+ B
                 D
        """
        ab = PathFactory.create(name="AB", geom=LineString((998522.520690918, 6381896.4595642),
                                                           (997785.990158081, 6381124.21846007),
                                                           (998272.546691896, 6380561.77696227),
                                                           (999629.548400879, 6381209.03106688)))
        cd = PathFactory.create(name="CD", geom=LineString((998522.520690918, 6381896.4595642),
                                                           (999098.044800479, 6380955.51783641)))
        ab.reload()
        cd.reload()
        self.assertEqual(len(Path.objects.all()), 3)

    def test_split_multiple(self):
        """

             C   E   G   I
             +   +   +   +
             |   |   |   |
        A +--+---+---+---+--+ B
             |   |   |   |
             +   +   +   +
             D   F   H   J
        """
        PathFactory.create(name="CD", geom=LineString((1, -2), (1, 2)))
        PathFactory.create(name="EF", geom=LineString((2, -2), (2, 2)))
        PathFactory.create(name="GH", geom=LineString((3, -2), (3, 2)))
        PathFactory.create(name="IJ", geom=LineString((4, -2), (4, 2)))
        PathFactory.create(name="AB", geom=LineString((0,  0), (5, 0)))

        self.assertEqual(len(Path.objects.filter(name="CD")), 2)
        self.assertEqual(len(Path.objects.filter(name="EF")), 2)
        self.assertEqual(len(Path.objects.filter(name="GH")), 2)
        self.assertEqual(len(Path.objects.filter(name="IJ")), 2)
        self.assertEqual(len(Path.objects.filter(name="AB")), 5)

    def test_split_multiple_2(self):
        """

             C   E   G   I
             +   +   +   +
             |   |   |   |
             |   |   |   |
        A +--+---+---+---+--+ B
             D   F   H   J
        """
        PathFactory.create(name="CD", geom=LineString((1, -2), (1, 2)))
        PathFactory.create(name="EF", geom=LineString((2, -2), (2, 2)))
        PathFactory.create(name="GH", geom=LineString((3, -2), (3, 2)))
        PathFactory.create(name="IJ", geom=LineString((4, -2), (4, 2)))
        PathFactory.create(name="AB", geom=LineString((0, -2), (5, -2)))

        self.assertEqual(len(Path.objects.filter(name="CD")), 1)
        self.assertEqual(len(Path.objects.filter(name="EF")), 1)
        self.assertEqual(len(Path.objects.filter(name="GH")), 1)
        self.assertEqual(len(Path.objects.filter(name="IJ")), 1)
        self.assertEqual(len(Path.objects.filter(name="AB")), 5)

    def test_split_multiple_3(self):
        """
               +            +
             E  \          /  F
        A +---+--+--------+--+---+ B
              |   \      /   |            AB exists. Create EF. Create CD.
              +----+----+----+
                    \  /
                     \/
        """
        PathFactory.create(name="AB", geom=LineString((0, 0), (10, 0)))
        PathFactory.create(name="EF", geom=LineString((2, 0), (2, -1), (8, -1), (8, 0)))

        PathFactory.create(name="CD", geom=LineString((2, 1), (5, -2), (8, 1)))

        self.assertEqual(len(Path.objects.filter(name="AB")), 5)
        self.assertEqual(len(Path.objects.filter(name="EF")), 3)
        self.assertEqual(len(Path.objects.filter(name="CD")), 5)

    def test_split_multiple_4(self):
        """
        Same as previous, without round values for intersections.

              C              D
               +            +
             E  \          /  F
        A +---+--+--------+--+---+ B
               \  \      /  /            AB exists. Create EF. Create CD.
                \  \    /  /
                 ---+--+---
                     \/
        """
        PathFactory.create(name="AB", geom=LineString((0, 0), (10, 0)))
        PathFactory.create(name="EF", geom=LineString((2, 0), (2, -1), (8, -1), (8, 0)))

        PathFactory.create(name="CD", geom=LineString((2, 1), (5, -2), (8, 1)))
        PathFactory.create(name="CD", geom=LineString((3, 1), (5, -2), (7, 1)))

        self.assertEqual(len(Path.objects.filter(name="AB")), 5)
        self.assertEqual(len(Path.objects.filter(name="EF")), 3)


class SplitPathLineTopologyTest(TransactionTestCase):

    def test_split_tee_1(self):
        """
                 C
        A +---===+===---+ B
             A'  |  B'
                 +      AB exists with topology A'B'.
                 D      Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.25, end=0.75)
        topogeom = topology.geom
        # Topology covers 1 path
        self.assertEqual(len(topology.paths.all()), 1)
        cd = PathFactory.create(geom=LineString((2, 0), (2, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        # Topology now covers 2 paths
        self.assertEqual(len(topology.paths.all()), 2)
        # AB and AB2 has one topology each
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 1)
        # Topology position became proportional
        aggr_ab = ab.aggregations.all()[0]
        aggr_cb = cb.aggregations.all()[0]
        self.assertEqual((0.5, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 0.5), (aggr_cb.start_position, aggr_cb.end_position))
        topology.reload()
        self.assertNotEqual(topology.geom, topogeom)
        self.assertEqual(topology.geom.coords[0], topogeom.coords[0])
        self.assertEqual(topology.geom.coords[-1], topogeom.coords[-1])

    def test_split_tee_1_reversed(self):
        """
                 C
        A +---===+===---+ B
             A'  |  B'
                 +      AB exists with topology A'B'.
                 D      Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.75, end=0.25, order=1)
        # Topology covers 1 path
        self.assertEqual(len(topology.paths.all()), 1)
        cd = PathFactory.create(geom=LineString((2, 0), (2, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        # Topology now covers 2 paths
        self.assertEqual(len(topology.paths.all()), 2)
        # AB and AB2 has one topology each
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 1)
        # Topology position became proportional
        aggr_ab = ab.aggregations.all()[0]
        aggr_cb = cb.aggregations.all()[0]
        self.assertEqual((1.0, 0.5), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.5, 0.0), (aggr_cb.start_position, aggr_cb.end_position))
        topology.reload()
        self.assertEqual(topology.geom, LineString((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), (1.0, 0.0, 0.0)))

    def test_split_tee_2(self):
        """
              C
        A +---+---=====--+ B
              |   A'  B'
              +           AB exists with topology A'B'.
              D           Add CD
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.5, end=0.75)
        topogeom = topology.geom
        # Topology covers 1 path
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(topology.paths.all()[0], ab)
        cd = PathFactory.create(geom=LineString((1, 0), (1, 2)))
        # CB was just created
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        # AB has no topology anymore
        self.assertEqual(len(ab.aggregations.all()), 0)
        # Topology now still covers 1 path, but the new one
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 1)
        self.assertEqual(topology.paths.all()[0].pk, cb.pk)
        topology.reload()
        self.assertEqual(topology.geom, topogeom)

    def test_split_tee_2_reversed(self):
        """
              C
        A +---+---=====--+ B
              |   A'  B'
              +           AB exists with topology A'B'.
              D           Add CD
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.75, end=0.5)
        topogeom = topology.geom
        # Topology covers 1 path
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(topology.paths.all()[0], ab)
        cd = PathFactory.create(geom=LineString((1, 0), (1, 2)))
        # CB was just created
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        # AB has no topology anymore
        self.assertEqual(len(ab.aggregations.all()), 0)
        # Topology now still covers 1 path, but the new one
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 1)
        self.assertEqual(topology.paths.all()[0].pk, cb.pk)
        topology.reload()
        self.assertEqual(topology.geom, topogeom)

    def test_split_tee_3(self):
        """
                    C
        A +--=====--+---+ B
             A'  B' |
                    +    AB exists with topology A'B'.
                    D    Add CD
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.3, end=0.6)
        topogeom = topology.geom
        # Topology covers 1 path
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(topology.paths.all()[0], ab)
        cd = PathFactory.create(geom=LineString((3, 0), (3, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        # CB does not have any
        self.assertEqual(len(cb.aggregations.all()), 0)

        # AB has still its topology
        self.assertEqual(len(ab.aggregations.all()), 1)
        # But start/end have changed
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual((0.4, 0.8), (aggr_ab.start_position, aggr_ab.end_position))
        topology.reload()
        self.assertEqual(topology.geom, topogeom)

    def test_split_tee_3_reversed(self):
        """
                    C
        A +--=====--+---+ B
             A'  B' |
                    +    AB exists with topology A'B'.
                    D    Add CD
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.45, end=0.15)
        topogeom = topology.geom
        # Topology covers 1 path
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(topology.paths.all()[0], ab)
        cd = PathFactory.create(geom=LineString((3, 0), (3, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        # CB does not have any
        self.assertEqual(len(cb.aggregations.all()), 0)

        # AB has still its topology
        self.assertEqual(len(ab.aggregations.all()), 1)
        # But start/end have changed
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual((0.6, 0.2), (aggr_ab.start_position, aggr_ab.end_position))
        topology.reload()
        self.assertEqual(topology.geom, LineString((1.7999999999999998, 0.0, 0.0), (0.5999999999999996, 0.0, 0.0)))

    def test_split_tee_4(self):
        """
                B   C   E
        A +--===+===+===+===--+ F
                    |
                    +    AB, BE, EF exist. A topology exists along them.
                    D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (2, 0)))
        be = PathFactory.create(name="BE", geom=LineString((2, 0), (4, 0)))
        ef = PathFactory.create(name="EF", geom=LineString((4, 0), (6, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.5, end=1)
        topology.add_path(be, start=0, end=1)
        topology.add_path(ef, start=0.0, end=0.5)
        topogeom = topology.geom

        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(be.aggregations.all()), 1)
        self.assertEqual(len(ef.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 3)
        # Create CD
        cd = PathFactory.create(geom=LineString((3, 0), (3, 2)))
        # Topology now covers 4 paths
        self.assertEqual(len(topology.paths.all()), 4)
        # AB and EF have still their topology
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(ef.aggregations.all()), 1)

        # BE and CE have one topology from 0.0 to 1.0
        bc = Path.objects.filter(pk=be.pk)[0]
        ce = Path.objects.filter(name="BE").exclude(pk=be.pk)[0]
        self.assertEqual(len(bc.aggregations.all()), 1)
        self.assertEqual(len(ce.aggregations.all()), 1)
        aggr_bc = bc.aggregations.all()[0]
        aggr_ce = ce.aggregations.all()[0]
        self.assertEqual((0.0, 1.0), (aggr_bc.start_position, aggr_bc.end_position))
        self.assertEqual((0.0, 1.0), (aggr_ce.start_position, aggr_ce.end_position))
        topology.reload()
        self.assertEqual(len(topology.aggregations.all()), 4)
        # Geometry has changed
        self.assertNotEqual(topology.geom, topogeom)
        # But extremities are equal
        self.assertEqual(topology.geom.coords[0], topogeom.coords[0])
        self.assertEqual(topology.geom.coords[-1], topogeom.coords[-1])

    def test_split_tee_4_reversed(self):
        """
                B   C   E
        A +--===+===+===+===--+ F
                    |
                    +    AB, BE, EF exist. A topology exists along them.
                    D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (2, 0)))
        be = PathFactory.create(name="BE", geom=LineString((4, 0), (2, 0)))
        ef = PathFactory.create(name="EF", geom=LineString((4, 0), (6, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.5, end=1)
        topology.add_path(be, start=1, end=0)
        topology.add_path(ef, start=0.0, end=0.5)

        # Create CD
        cd = PathFactory.create(name="DC", geom=LineString((3, 0), (3, 2)))
        # Topology now covers 4 paths
        topology.reload()
        self.assertEqual(len(topology.paths.all()), 4)
        # BE and CE have one topology from 0.0 to 1.0
        bc = Path.objects.filter(pk=be.pk)[0]
        ce = Path.objects.filter(name="BE").exclude(pk=be.pk)[0]
        aggr_ab = ab.aggregations.all()[0]
        aggr_bc = bc.aggregations.all()[0]
        aggr_ce = ce.aggregations.all()[0]
        aggr_ef = ef.aggregations.all()[0]
        self.assertEqual((0.5, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((1.0, 0.0), (aggr_bc.start_position, aggr_bc.end_position))
        self.assertEqual((1.0, 0.0), (aggr_ce.start_position, aggr_ce.end_position))
        self.assertEqual((0.0, 0.5), (aggr_ef.start_position, aggr_ef.end_position))
        topology.reload()
        self.assertEqual(len(topology.aggregations.all()), 4)
        # Geometry has changed
        self.assertEqual(topology.geom, LineString((1.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                                                   (3.0, 0.0, 0.0), (4.0, 0.0, 0.0),
                                                   (5.0, 0.0, 0.0)))

    def test_split_twice(self):
        """

             C   D
             +   +
             |   |
      A +--==+===+==--+ B
             |   |
             +---+
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.1, end=0.9)
        topogeom = topology.geom
        self.assertEqual(len(topology.paths.all()), 1)
        cd = PathFactory.create(name="CD", geom=LineString((1, 2), (1, -2),
                                                           (3, -2), (3, 2)))
        self.assertEqual(len(topology.paths.all()), 3)
        self.assertEqual(len(ab.aggregations.all()), 1)
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual((0.4, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        ab2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        ab3 = Path.objects.filter(name="AB").exclude(pk__in=[ab.pk, ab2.pk])[0]
        if ab2.geom.length < ab3.geom.length:
            ab2, ab3 = ab3, ab2
        aggr_ab2 = ab2.aggregations.all()[0]
        aggr_ab3 = ab3.aggregations.all()[0]
        self.assertEqual((0.0, 1.0), (aggr_ab2.start_position, aggr_ab2.end_position))
        self.assertEqual((0.0, 0.6), (aggr_ab3.start_position, aggr_ab3.end_position))
        topology.reload()
        self.assertNotEqual(topology.geom, topogeom)
        self.assertEqual(topology.geom.coords[0], topogeom.coords[0])
        self.assertEqual(topology.geom.coords[-1], topogeom.coords[-1])

    def test_split_twice_reversed(self):
        """

             C   D
             +   +
             |   |
      A +--==+===+==--+ B
             |   |
             +---+
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.9, end=0.1, order=1)
        topogeom = topology.geom
        self.assertEqual(len(topology.paths.all()), 1)
        cd = PathFactory.create(name="CD", geom=LineString((1, 2), (1, -2),
                                                           (3, -2), (3, 2)))
        self.assertEqual(len(topology.paths.all()), 3)
        self.assertEqual(len(ab.aggregations.all()), 1)
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual((1.0, 0.4), (aggr_ab.start_position, aggr_ab.end_position))
        ab2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        ab3 = Path.objects.filter(name="AB").exclude(pk__in=[ab.pk, ab2.pk])[0]
        aggr_ab2 = ab2.aggregations.all()[0]
        aggr_ab3 = ab3.aggregations.all()[0]
        self.assertEqual((1.0, 0.0), (aggr_ab2.start_position, aggr_ab2.end_position))
        self.assertEqual((0.6, 0.0), (aggr_ab3.start_position, aggr_ab3.end_position))
        topology.reload()
        self.assertEqual(topology.geom, LineString((3.6000000000000001, 0), (3, 0),
                                                   (1.0, 0.0), (0.4, 0.0)))

    def test_split_on_update(self):
        """                               + E
                                          :
                                         ||
        A +-----------+ B         A +----++---+ B
                                         ||
        C +-====-+ D              C +--===+ D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, -1), (4, -1)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.3, end=0.9)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((0, -1), (2, -1), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 2)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(cd2.aggregations.all()), 1)
        aggr_cd = cd.aggregations.all()[0]
        aggr_cd2 = cd2.aggregations.all()[0]
        self.assertEqual((0.5, 1.0), (aggr_cd.start_position, aggr_cd.end_position))
        self.assertEqual((0.0, 0.75), (aggr_cd2.start_position, aggr_cd2.end_position))

    def test_split_on_update_2(self):
        """                               + E
                                          :
                                          :
        A +-----------+ B         A +-----+---+ B
                                          :
        C +-==------+ D           C +--===+ D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, -1), (4, -1)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.15, end=0.3)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((0, -1), (2, -1), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(cd2.aggregations.all()), 0)
        aggr_cd = cd.aggregations.all()[0]
        self.assertEqual((0.25, 0.5), (aggr_cd.start_position, aggr_cd.end_position))

    def test_split_on_update_3(self):
        """                               + E
                                          ||
                                          ||
        A +-----------+ B         A +-----+---+ B
                                          :
        C +------==-+ D           C +-----+ D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, -1), (4, -1)))
        # Create a topology
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.7, end=0.85)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((0, -1), (2, -1), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 0)
        self.assertEqual(len(cd2.aggregations.all()), 1)
        aggr_cd2 = cd2.aggregations.all()[0]
        self.assertEqual((0.25, 0.625), (aggr_cd2.start_position, aggr_cd2.end_position))

    def test_split_on_return_topology(self):
        """
            A       B       C       D
            +-------+-------+-------+
                >=================+
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        bc = PathFactory.create(name="BC", geom=LineString((4, 0), (8, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((8, 0), (12, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.5, end=1, order=1)
        topology.add_path(bc, start=0, end=1, order=2)
        topology.add_path(cd, start=0.0, end=0.5, order=3)
        topology.add_path(cd, start=0.5, end=0.5, order=4)
        topology.add_path(cd, start=0.5, end=0.0, order=5)
        topology.add_path(bc, start=1, end=0, order=6)
        topology.add_path(ab, start=1, end=0.5, order=7)
        self.assertEqual(len(topology.aggregations.all()), 7)

        topogeom = topology.geom

        PathFactory.create(name="split", geom=LineString((9, -1), (9, 1)))
        topology.reload()
        self.assertItemsEqual(topology.aggregations.order_by('order').values_list('order', 'path__name'),
                              [(1, 'AB'), (2, 'BC'), (3, 'CD'), (3, 'CD'), (4, 'CD'),
                               (5, 'CD'), (5, 'CD'), (6, 'BC'), (7, 'AB')])
        self.assertTrue(topology.geom.equals(topogeom))


class SplitPathPointTopologyTest(TransactionTestCase):

    def test_split_tee_1(self):
        """
                C
        A +-----X----+ B
                |
                +    AB exists with topology at C.
                D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.5, end=0.5)
        self.assertEqual(len(topology.paths.all()), 1)

        cd = PathFactory.create(geom=LineString((2, 0), (2, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        self.assertEqual(len(topology.paths.all()), 3)
        self.assertEqual(len(ab.aggregations.all()), 1)
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual(len(cb.aggregations.all()), 1)
        aggr_cb = cb.aggregations.all()[0]
        self.assertEqual(len(cd.aggregations.all()), 1)
        aggr_cd = cd.aggregations.all()[0]
        self.assertEqual((1.0, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 0.0), (aggr_cb.start_position, aggr_cb.end_position))
        self.assertEqual((0.0, 0.0), (aggr_cd.start_position, aggr_cd.end_position))

    def test_split_tee_2(self):
        """
                C
        A +--X--+----+ B
                |
                +    AB exists.
                D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.25, end=0.25)
        self.assertEqual(len(topology.paths.all()), 1)
        PathFactory.create(geom=LineString((2, 0), (2, 2)))
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 1)
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual((0.5, 0.5), (aggr_ab.start_position, aggr_ab.end_position))

    def test_split_tee_3(self):
        """
                C
        A +-----+--X--+ B
                |
                +    AB exists.
                D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.75, end=0.75)
        self.assertEqual(len(topology.paths.all()), 1)
        PathFactory.create(geom=LineString((2, 0), (2, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 0)
        self.assertEqual(len(cb.aggregations.all()), 1)
        aggr_cb = cb.aggregations.all()[0]
        self.assertEqual((0.5, 0.5), (aggr_cb.start_position, aggr_cb.end_position))

    def test_split_tee_4(self):
        """
                C
        A X-----+----+ B
                |
                +    AB exists.
                D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.0, end=0.0)
        self.assertEqual(len(topology.paths.all()), 1)
        PathFactory.create(geom=LineString((2, 0), (2, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 0)
        aggr_ab = ab.aggregations.all()[0]
        self.assertEqual((0.0, 0.0), (aggr_ab.start_position, aggr_ab.end_position))

    def test_split_tee_5(self):
        """
                C
        A +-----+----X B
                |
                +    AB exists.
                D    Add CD.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=1.0, end=1.0)
        self.assertEqual(len(topology.paths.all()), 1)
        PathFactory.create(name="CD", geom=LineString((2, 0), (2, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 0)
        self.assertEqual(len(cb.aggregations.all()), 1)
        aggr_cb = cb.aggregations.all()[0]
        self.assertEqual((1.0, 1.0), (aggr_cb.start_position, aggr_cb.end_position))

    def test_split_tee_6(self):
        """
            X
                C
        A +-----+-----+ B
                |
                +    AB exists. Add CD.
                D    Point with offset is now linked to AC.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (8, 0)))

        poi = Point(1, 3, srid=settings.SRID)
        poi.transform(settings.API_SRID)
        topology = Topology.deserialize({'lat': poi.y, 'lng': poi.x})
        aggr = topology.aggregations.all()[0]
        position = topology.geom.coords

        self.assertTrue(almostequal(3, topology.offset))
        self.assertTrue(almostequal(0.125, aggr.start_position))
        self.assertTrue(almostequal(0.125, aggr.end_position))

        # Add CD
        PathFactory.create(name="CD", geom=LineString((4, 0), (4, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        aggr_ab = ab.aggregations.all()[0]

        topology.reload()
        self.assertTrue(almostequal(3, topology.offset))
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 0)
        self.assertEqual(position, topology.geom.coords)
        self.assertTrue(almostequal(0.5, aggr_ab.start_position))
        self.assertTrue(almostequal(0.5, aggr_ab.end_position))

    def test_split_tee_7(self):
        """
                    X
                C
        A +-----+-----+ B
                |
                +    AB exists. Add CD.
                D    Point with offset is now linked to CB.
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (8, 0)))

        poi = Point(7, 3, srid=settings.SRID)
        poi.transform(settings.API_SRID)
        topology = Topology.deserialize({'lat': poi.y, 'lng': poi.x})
        aggr = topology.aggregations.all()[0]
        position = topology.geom.coords

        self.assertTrue(almostequal(3, topology.offset))
        self.assertTrue(almostequal(0.875, aggr.start_position))
        self.assertTrue(almostequal(0.875, aggr.end_position))

        # Add CD
        PathFactory.create(name="CD", geom=LineString((4, 0), (4, 2)))
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]


        topology.reload()
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 0)
        self.assertEqual(len(cb.aggregations.all()), 1)
        self.assertTrue(almostequal(3, topology.offset), topology.offset)
        self.assertEqual(position, topology.geom.coords)
        aggr_cb = cb.aggregations.all()[0]
        self.assertTrue(almostequal(0.75, aggr_cb.start_position))
        self.assertTrue(almostequal(0.75, aggr_cb.end_position))

    def test_split_on_update(self):
        """                               + D
                                          :
                                          :
        A +-----------+ B         A +-----X---+ B
                                          :
        C +---X---+ D              C +----+
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))

        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.5, end=0.5)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, -2), (2, 2))
        cd.save()
        ab2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]

        self.assertEqual(len(ab2.aggregations.all()), 1)
        self.assertEqual(len(cd2.aggregations.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 4)

        aggr_ab = ab.aggregations.all()[0]
        aggr_ab2 = ab2.aggregations.all()[0]
        aggr_cd = cd.aggregations.all()[0]
        aggr_cd2 = cd2.aggregations.all()[0]
        self.assertEqual((1.0, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 0.0), (aggr_ab2.start_position, aggr_ab2.end_position))
        self.assertEqual((1.0, 1.0), (aggr_cd.start_position, aggr_cd.end_position))
        self.assertEqual((0.0, 0.0), (aggr_cd2.start_position, aggr_cd2.end_position))

    def test_split_on_update_2(self):
        """                               + D
                                          :
                                          :
        A +-----------+ B         A +-----+---+ B
                                          :
        C +-X-----+ D              C +--X-+
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.25, end=0.25)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, -2), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(cd2.aggregations.all()), 0)
        aggr_cd = cd.aggregations.all()[0]
        self.assertEqual((0.5, 0.5), (aggr_cd.start_position, aggr_cd.end_position))

    def test_split_on_update_3(self):
        """                               + E
                                          X
                                          :
        A +-----------+ B         A +-----+---+ B
                                          :
        C +-----X-+ D              C +----+ D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.75, end=0.75)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, -2), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 0)
        self.assertEqual(len(cd2.aggregations.all()), 1)
        aggr_cd2 = cd2.aggregations.all()[0]
        self.assertEqual((0.5, 0.5), (aggr_cd2.start_position, aggr_cd2.end_position))

    def test_split_on_update_4(self):
        """                               + E
                                          :
                                          :
        A +-----------+ B         A +-----+---+ B
                                          :
        C X-------+ D              C X----+ D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.0, end=0.0)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, -2), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(cd2.aggregations.all()), 0)
        aggr_cd = cd.aggregations.all()[0]
        self.assertEqual((0.0, 0.0), (aggr_cd.start_position, aggr_cd.end_position))

    def test_split_on_update_5(self):
        """                               X E
                                          :
                                          :
        A +-----------+ B         A +-----+---+ B
                                          :
        C +-------X D              C +----+ D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=1.0, end=1.0)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, -2), (2, 2))
        cd.save()
        cd2 = Path.objects.filter(name="CD").exclude(pk=cd.pk)[0]
        self.assertEqual(len(topology.paths.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 0)
        self.assertEqual(len(cd2.aggregations.all()), 1)
        aggr_cd2 = cd2.aggregations.all()[0]
        self.assertEqual((1.0, 1.0), (aggr_cd2.start_position, aggr_cd2.end_position))

    def test_split_on_update_6(self):
        """
                                          D
        A +-----------+ B         A +-----X---+ B
                                          :
        C +-------X D                     :
                                          +
                                          C
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=1.0, end=1.0)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, -2), (2, 0))
        cd.save()
        db = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(db.aggregations.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 3)

        aggr_ab = ab.aggregations.all()[0]
        aggr_db = db.aggregations.all()[0]
        aggr_cd = cd.aggregations.all()[0]
        self.assertEqual((1.0, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 0.0), (aggr_db.start_position, aggr_db.end_position))
        self.assertEqual((1.0, 1.0), (aggr_cd.start_position, aggr_cd.end_position))

    def test_split_on_update_7(self):
        """
                                          C
        A +-----------+ B         A +-----X---+ B
                                          :
        C X-------+ D                     :
                                          + D
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0)))
        cd = PathFactory.create(name="CD", geom=LineString((0, 1), (4, 1)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(cd, start=0.0, end=0.0)
        self.assertEqual(len(topology.paths.all()), 1)

        cd.geom = LineString((2, 0), (2, -2))
        cd.save()
        cb = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]

        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 1)
        self.assertEqual(len(cd.aggregations.all()), 1)
        self.assertEqual(len(topology.paths.all()), 3)

        aggr_ab = ab.aggregations.all()[0]
        aggr_cb = cb.aggregations.all()[0]
        aggr_cd = cd.aggregations.all()[0]
        self.assertEqual((1.0, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 0.0), (aggr_cb.start_position, aggr_cb.end_position))
        self.assertEqual((0.0, 0.0), (aggr_cd.start_position, aggr_cd.end_position))


class SplitPathGenericTopologyTest(TransactionTestCase):

    def test_add_simple_path(self):
        """
        A +--==          ==----+ C
               \\      //
                \\    //
                 ==+==
                   B
        Add path:

               D        E
        A +--==+--------+==----+ C
               \\      //
                \\    //
                 ==+==
                   B
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0),
                                                           (6, -2), (8, -2)))
        bc = PathFactory.create(name="BC", geom=LineString((8, -2), (10, -2),
                                                           (12, 0), (14, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.25, end=1.0)
        topology.add_path(bc, start=0.0, end=0.75)
        self.assertEqual(len(topology.paths.all()), 2)
        originalgeom = LineString((2.2071067811865475, 0), (4, 0), (6, -2), (8, -2), (10, -2), (12, 0), (12.2928932188134521, 0))
        self.assertEqual(topology.geom, originalgeom)

        # Add a path
        de = PathFactory.create(name="DE", geom=LineString((4, 0), (12, 0)))
        self.assertEqual(len(Path.objects.all()), 5)
        ab_2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        bc_2 = Path.objects.filter(name="BC").exclude(pk=bc.pk)[0]

        # Topology aggregations were updated
        topology.reload()
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(ab_2.aggregations.all()), 1)
        self.assertEqual(len(bc.aggregations.all()), 1)
        self.assertEqual(len(bc_2.aggregations.all()), 1)
        self.assertEqual(len(de.aggregations.all()), 0)
        aggr_ab = ab.aggregations.all()[0]
        aggr_ab2 = ab_2.aggregations.all()[0]
        aggr_bc = bc.aggregations.all()[0]
        aggr_bc2 = bc_2.aggregations.all()[0]
        self.assertEqual((0.551776695296637, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 1.0), (aggr_ab2.start_position, aggr_ab2.end_position))
        self.assertEqual((0.0, 1.0), (aggr_bc.start_position, aggr_bc.end_position))
        self.assertEqual((0.0, 0.146446609406726), (aggr_bc2.start_position, aggr_bc2.end_position))

        # But topology resulting geometry did not change
        self.assertEqual(topology.geom, originalgeom)

    def test_add_path_converge(self):
        """
        A +--==          ==----+ C
               \\      //
                \\    //
                 ==+==
                   B
        Add path:

               D        E
        A +--==+--------+==----+ C
               \\      //
                \\    //
                 ==+==
                   B
        """
        ab = PathFactory.create(name="AB", geom=LineString((0, 0), (4, 0),
                                                           (6, -2), (8, -2)))
        cb = PathFactory.create(name="CB", geom=LineString((14, 0), (12, 0),
                                                           (10, -2), (8, -2)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ab, start=0.25, end=1.0)
        topology.add_path(cb, start=1.0, end=0.25)
        self.assertEqual(len(topology.paths.all()), 2)
        originalgeom = LineString((2.2071067811865475, 0), (4, 0), (6, -2), (8, -2), (10, -2), (12, 0), (12.2928932188134521, 0))
        self.assertEqual(topology.geom, originalgeom)

        # Add a path
        de = PathFactory.create(name="DE", geom=LineString((4, 0), (12, 0)))
        self.assertEqual(len(Path.objects.all()), 5)
        ab_2 = Path.objects.filter(name="AB").exclude(pk=ab.pk)[0]
        cb_2 = Path.objects.filter(name="CB").exclude(pk=cb.pk)[0]

        # Topology aggregations were updated
        topology.reload()
        self.assertEqual(len(ab.aggregations.all()), 1)
        self.assertEqual(len(ab_2.aggregations.all()), 1)
        self.assertEqual(len(cb.aggregations.all()), 1)
        self.assertEqual(len(cb_2.aggregations.all()), 1)
        self.assertEqual(len(de.aggregations.all()), 0)
        aggr_ab = ab.aggregations.all()[0]
        aggr_ab2 = ab_2.aggregations.all()[0]
        aggr_cb = cb.aggregations.all()[0]
        aggr_cb2 = cb_2.aggregations.all()[0]
        self.assertEqual((0.551776695296637, 1.0), (aggr_ab.start_position, aggr_ab.end_position))
        self.assertEqual((0.0, 1.0), (aggr_ab2.start_position, aggr_ab2.end_position))
        self.assertEqual((1.0, 0.0), (aggr_cb2.start_position, aggr_cb2.end_position))
        self.assertEqual((1.0, 0.853553390593274), (aggr_cb.start_position, aggr_cb.end_position))

        # But topology resulting geometry did not change
        self.assertEqual(topology.geom, originalgeom)

    def test_add_path_diverge(self):
        """
        A +--==          ==----+ C
               \\      //
                \\    //
                 ==+==
                   B
        Add path:

               D        E
        A +--==+--------+==----+ C
               \\      //
                \\    //
                 ==+==
                   B
        """
        ba = PathFactory.create(name="BA", geom=LineString((8, -2), (6, -2),
                                                           (4, 0), (0, 0)))
        bc = PathFactory.create(name="BC", geom=LineString((8, -2), (10, -2),
                                                           (12, 0), (14, 0)))
        topology = TopologyFactory.create(no_path=True)
        topology.add_path(ba, start=0.75, end=0.0, order=1)
        topology.add_path(bc, start=0.0, end=0.75, order=2)
        self.assertEqual(len(topology.paths.all()), 2)
        originalgeom = LineString((2.2071067811865475, 0), (4, 0), (6, -2), (8, -2), (10, -2), (12, 0), (12.2928932188134521, 0))
        self.assertEqual(topology.geom, originalgeom)

        # Add a path
        de = PathFactory.create(name="DE", geom=LineString((4, 0), (12, 0)))
        self.assertEqual(len(Path.objects.all()), 5)
        ba_2 = Path.objects.filter(name="BA").exclude(pk=ba.pk)[0]
        bc_2 = Path.objects.filter(name="BC").exclude(pk=bc.pk)[0]

        # Topology aggregations were updated
        topology.reload()
        self.assertEqual(len(ba.aggregations.all()), 1)
        self.assertEqual(len(ba_2.aggregations.all()), 1)
        self.assertEqual(len(bc.aggregations.all()), 1)
        self.assertEqual(len(bc_2.aggregations.all()), 1)
        self.assertEqual(len(de.aggregations.all()), 0)
        aggr_ba = ba.aggregations.all()[0]
        aggr_ba2 = ba_2.aggregations.all()[0]
        aggr_bc = bc.aggregations.all()[0]
        aggr_bc2 = bc_2.aggregations.all()[0]
        self.assertEqual((0.448223304703363, 0.0), (aggr_ba2.start_position, aggr_ba2.end_position))
        self.assertEqual((1.0, 0.0), (aggr_ba.start_position, aggr_ba.end_position))
        self.assertEqual((0.0, 1.0), (aggr_bc.start_position, aggr_bc.end_position))
        self.assertEqual((0.0, 0.146446609406726), (aggr_bc2.start_position, aggr_bc2.end_position))

        # But topology resulting geometry did not change
        originalgeom = LineString((2.2071067811865470, 0), *originalgeom[1:])
        self.assertEqual(topology.geom, originalgeom)
