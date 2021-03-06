from django.test import TestCase

from paperclip.models import Attachment
from paperclip.views import add_url_for_obj

from geotrek.authent.factories import PathManagerFactory
from geotrek.core.factories import PathFactory
from geotrek.common.factories import AttachmentFactory, FileTypeFactory
from geotrek.common.utils.testdata import get_dummy_uploaded_image


class PathAttachmentTestCase(TestCase):
    """Simple test checking list and upload of attachments"""

    def setUp(self):
        self.password = 'toto'
        self.user = PathManagerFactory(password=self.password)
        self.assertTrue(self.client.login(username=self.user.username, password=self.password))

    def test_list_attachments_in_details(self):
        """Test that the list is correctly displayed on the detail page of path"""

        path = PathFactory(length=1)
        AttachmentFactory(obj=path, creator=self.user)

        response = self.client.get(path.get_detail_url())

        self.assertTemplateUsed(response, template_name='paperclip/details.html')
        self.assertItemsEqual(Attachment.objects.attachments_for_object(path),
                              response.context['attachments_list'], )

    def test_upload(self):
        path = PathFactory(length=1)
        response = self.client.get(path.get_update_url())

        f = get_dummy_uploaded_image()
        data = {
            'filetype': FileTypeFactory().pk,
            'title': 'title1',
            'legend': 'legend1',
            'attachment_file': f,
        }

        response = self.client.post(add_url_for_obj(path), data=data)
        self.assertEquals(response.status_code, 302)

        att = Attachment.objects.attachments_for_object(path).get()
        self.assertEqual(att.title, data['title'])
        self.assertEqual(att.legend, data['legend'])
        self.assertEqual(att.filetype.pk, data['filetype'])

        f.open()
        self.assertEqual(att.attachment_file.readlines(), f.readlines())

        # Check that if title is given, filename is title
        self.assertTrue(att.attachment_file.name, 'title1')

        # Check that if no title is give, filename is original name
        data['title'] = ''
        response = self.client.post(add_url_for_obj(path), data=data)
        att = Attachment.objects.attachments_for_object(path)[0]
        self.assertTrue(att.attachment_file.name, 'image')
