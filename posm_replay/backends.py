import os
import threading
from xml.dom import minidom

from social_core.backends.openstreetmap import OpenStreetMapOAuth

from replay_tool.models import UpstreamChangeSet, OSMElement
from replay_tool.utils.common import create_changeset_creation_xml
from replay_tool.utils.common import get_aoi_name
from replay_tool.tasks import create_and_push_changeset

import logging

logger = logging.getLogger('__name__')


class CustomOSMOAuth(OpenStreetMapOAuth):
    AUTHORIZATION_URL = os.environ['AUTHORIZE_URL']
    REQUEST_TOKEN_URL = os.environ['REQUEST_TOKEN_URL']
    ACCESS_TOKEN_URL = os.environ['ACCESS_TOKEN_URL']
    API_URL = os.environ.get('OAUTH_API_URL', 'https://master.apis.dev.openstreetmap.org')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.osm_user = None
        self._access_token = None  # self.access_token is already a method

    def oauth_request(self, token, url, params=None, method='GET', data=None, headers={}):
        """Generate OAuth request, setups callback url"""
        return self.request(url, method=method, params=params,
                            auth=self.oauth_auth(token), headers=headers, data=data)

    def user_data(self, access_token, *args, **kwargs):
        """Return user data provided"""
        self._access_token = access_token
        url = os.path.join(self.API_URL, 'api/0.6/user/details')
        response = self.oauth_request(
            access_token, url
        )
        try:
            dom = minidom.parseString(response.content)
        except ValueError:
            return None
        self.osm_user = dom.getElementsByTagName('user')[0]
        username = self.osm_user.getAttribute('display_name')
        try:
            avatar = dom.getElementsByTagName('img')[0].getAttribute('href')
        except IndexError:
            avatar = None

        thread = threading.Thread(
            target=create_and_push_changeset,
            args=(self,),
            daemon=True,
        )
        thread.start()

        return {
            'id': self.osm_user and self.osm_user.getAttribute('id'),
            'username': username,
            'account_created': self.osm_user and self.osm_user.getAttribute('account_created'),
            'avatar': avatar,
            'access_token': access_token,
        }

    def get_or_create_changeset(self):
        # NOTE: To avoid stale changesets upstream, create new every time
        UpstreamChangeSet.objects.all().delete()

        # Create a changeset
        aoiname = get_aoi_name()
        comment = f"Updates on POSM in area '{aoiname}'"
        # TODO: get version
        version = '1.1'
        create_changeset_xml = create_changeset_creation_xml(comment, version)

        url = os.path.join(self.API_URL, 'api/0.6/changeset/create')
        logger.info(f'OSM API URL: {url}')
        response = self.oauth_request(
            self._access_token, url, method='PUT',
            headers={'Content-Type': 'text/xml'},
            data=create_changeset_xml,
        )

        logger.info(response.text)

        if not response.status_code == 200:
            raise Exception(f'Could not create changeset. Error: {response.text}')

        changeset_id = int(response.text)
        return UpstreamChangeSet.objects.create(changeset_id=changeset_id)

    def upload_changeset(self, changeset_id):
        changeset_xml = OSMElement.get_upstream_changeset(changeset_id)

        url = os.path.join(self.API_URL, f'api/0.6/changeset/{changeset_id}/upload')
        logger.info(f'OSM API URL: {url}')
        response = self.oauth_request(
            self._access_token, url, method='POST',
            headers={'Content-Type': 'text/xml'},
            data=changeset_xml,
        )
        logger.info(response.text)

        if not response.status_code == 200:
            raise Exception(f'Could not upload changeset {changeset_id}. Error: {response.text}')

        return True

    def close_changeset(self, changeset_id):
        url = os.path.join(self.API_URL, f'api/0.6/changeset/{changeset_id}/close')
        logger.info(f'OSM API URL: {url}')
        response = self.oauth_request(
            self._access_token, url, method='PUT',
            headers={'Content-Type': 'text/xml'},
        )
        logger.info(response.text)
        if not response.status_code == 200:
            raise Exception(f'Could not close changeset {changeset_id}. Error: {response.text}')

        return True
