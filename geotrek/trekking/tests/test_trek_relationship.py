from django.test import TransactionTestCase
from django.db import DatabaseError

from ..factories import TrekFactory, TrekRelationshipFactory


class TrekRelationshipsTestCase(TransactionTestCase):

    def test_relationships(self):
        trek1 = TrekFactory()
        trek2 = TrekFactory()
        trek3 = TrekFactory()

        TrekRelationshipFactory(trek_a=trek1, trek_b=trek2)
        TrekRelationshipFactory(trek_a=trek2, trek_b=trek3)

        self.assertItemsEqual(trek1.related.all(), [trek2])
        self.assertItemsEqual(trek2.related.all(), [trek1, trek3])
        self.assertItemsEqual(trek3.related.all(), [trek2])

    def test_relationship_insertion(self):
        trek1 = TrekFactory()
        trek2 = TrekFactory()
        TrekRelationshipFactory(trek_a=trek1, trek_b=trek2)
        # This should fail, since it already exists
        self.assertRaises(DatabaseError, lambda: TrekRelationshipFactory(trek_a=trek2, trek_b=trek1))
