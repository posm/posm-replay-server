import os
from xml.dom import minidom

from social_core.backends.openstreetmap import OpenStreetMapOAuth

from replay_tool.models import UpstreamChangeSet, OSMElement
from replay_tool.utils.osm_api import create_changeset_creation_xml
from replay_tool.utils.common import get_aoi_name


class CustomOSMOAuth(OpenStreetMapOAuth):
    AUTHORIZATION_URL = os.environ['AUTHORISE_URL']
    REQUEST_TOKEN_URL = os.environ['REQUEST_TOKEN_URL']
    ACCESS_TOKEN_URL = os.environ['ACCESS_TOKEN_URL']
    API_URL = os.environ.get('OAUTH_API_URL', 'https://master.apis.dev.openstreetmap.org')

    def oauth_request(self, token, url, params=None, method='GET', data=None, headers={}):
        """Generate OAuth request, setups callback url"""
        return self.request(url, method=method, params=params,
                            auth=self.oauth_auth(token), headers=headers, data=data)

    def user_data(self, access_token, *args, **kwargs):
        """Return user data provided"""
        url = os.path.join(self.API_URL, 'api/0.6/user/details')
        response = self.oauth_request(
            access_token, url
        )
        try:
            dom = minidom.parseString(response.content)
        except ValueError:
            return None
        user = dom.getElementsByTagName('user')[0]
        username = user.getAttribute('display_name')
        try:
            avatar = dom.getElementsByTagName('img')[0].getAttribute('href')
        except IndexError:
            avatar = None

        changeset = self.get_or_create_changeset(access_token, username)

        self.upload_changeset(access_token, changeset.changeset_id)

        return {
            'id': user.getAttribute('id'),
            'username': username,
            'account_created': user.getAttribute('account_created'),
            'avatar': avatar,
            'access_token': access_token,
        }

    def get_or_create_changeset(self, access_token, user):
        changeset = UpstreamChangeSet.objects.filter(is_closed=False).first()
        if changeset:
            return changeset

        # Create a changeset
        aoiname = get_aoi_name()
        comment = f"Updates on POSM in area '{aoiname}'"
        # TODO: get version
        version = '1.1'
        create_changeset_xml = create_changeset_creation_xml(comment, version)

        url = 'https://master.apis.dev.openstreetmap.org/api/0.6/changeset/create'
        response = self.oauth_request(
            access_token, url, method='PUT',
            headers={'Content-Type': 'text/xml'},
            data=create_changeset_xml,
        )
        if not response.status_code == 200:
            raise Exception(f'Could not create changeset. Error: {response.text}')

        changeset_id = int(response.text)
        return UpstreamChangeSet.objects.create(changeset_id=changeset_id)

    def upload_changeset(self, access_token, changeset_id):
        changeset_xml = OSMElement.get_upstream_changeset(changeset_id)

        url = f'https://master.apis.dev.openstreetmap.org/api/0.6/changeset/{changeset_id}/upload'
        response = self.oauth_request(
            access_token, url, method='POST',
            headers={'Content-Type': 'text/xml'},
            data=changeset_xml,
        )
        print(response.text)

        if not response.status_code == 200:
            raise Exception(f'Could not upload changeset. Error: {response.text}')

        # TODO: close changeset
        return True
