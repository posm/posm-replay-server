import os
import six
import threading
from xml.dom import minidom
from requests import request, ConnectionError, HTTPError

from social_core.utils import SSLHttpAdapter, user_agent
from social_core.exceptions import AuthFailed
from social_core.backends.oauth import OAuth1
from social_core.backends.openstreetmap import OpenStreetMapOAuth

from replay_tool.models import UpstreamChangeSet, OSMElement, ReplayToolConfig
from replay_tool.utils.common import create_changeset_creation_xml
from replay_tool.utils.common import get_aoi_name
from replay_tool.tasks import create_and_push_changeset

import logging

logger = logging.getLogger('__name__')


class CustomOSMOAuth(OpenStreetMapOAuth):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.osm_user = None
        self._access_token = None  # self.access_token is already a method

    def oauth_request(self, token, url, params=None, method='GET', data=None, headers={}):
        """Generate OAuth request, setups callback url"""
        try:
            return self.request(url, method=method, params=params,
                                auth=self.oauth_auth(token), headers=headers, data=data)
        except Exception as e:
            raise e

    def user_data(self, access_token, *args, **kwargs):
        """Return user data provided"""
        self._access_token = access_token
        url = os.path.join(self.oauth_api_url(), 'api/0.6/user/details')
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

        # Call the task
        # NOTE: thread is used instead of celery task because "self" needs to be sent and
        # can't be serialized for celery.
        task = threading.Thread(target=create_and_push_changeset, args=(self,))
        task.start()

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

        url = os.path.join(self.oauth_api_url(), 'api/0.6/changeset/create')
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

        url = os.path.join(self.oauth_api_url(), f'api/0.6/changeset/{changeset_id}/upload')
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
        url = os.path.join(self.oauth_api_url(), f'api/0.6/changeset/{changeset_id}/close')
        logger.info(f'OSM API URL: {url}')
        response = self.oauth_request(
            self._access_token, url, method='PUT',
            headers={'Content-Type': 'text/xml'},
        )
        logger.info(response.text)
        if not response.status_code == 200:
            raise Exception(f'Could not close changeset {changeset_id}. Error: {response.text}')

        return True

    def get_key_and_secret(self):
        """Return tuple with Consumer Key and Consumer Secret for current
        service provider. Must return (key, secret), order *must* be respected.
        """
        config = ReplayToolConfig.load()
        return config.oauth_consumer_key, config.oauth_consumer_secret

    def authorization_url(self):
        config = ReplayToolConfig.load()
        return config.authorization_url

    def access_token_url(self):
        config = ReplayToolConfig.load()
        return config.access_token_url

    def request_token_url(self):
        config = ReplayToolConfig.load()
        return config.request_token_url

    def oauth_api_url(self):
        config = ReplayToolConfig.load()
        return config.oauth_api_url

    def unauthorized_token(self):
        """Return request for unauthorized token (first stage)"""
        params = self.request_token_extra_arguments()
        params.update(self.get_scope_argument())
        key, secret = self.get_key_and_secret()
        # decoding='utf-8' produces errors with python-requests on Python3
        # since the final URL will be of type bytes
        decoding = None if six.PY3 else 'utf-8'
        state = self.get_or_create_state()
        response = self.request(
            self.request_token_url(),
            params=params,
            auth=OAuth1(key, secret, callback_uri=self.get_redirect_uri(state),
                        decoding=decoding),
            method=self.REQUEST_TOKEN_METHOD
        )
        content = response.content
        if response.encoding or response.apparent_encoding:
            content = content.decode(response.encoding or
                                     response.apparent_encoding)
        else:
            content = response.content.decode()
        return content

    # Overriding this method just to capture response text
    def request(self, url, method='GET', *args, **kwargs):
        kwargs.setdefault('headers', {})
        if self.setting('VERIFY_SSL') is not None:
            kwargs.setdefault('verify', self.setting('VERIFY_SSL'))
        kwargs.setdefault('timeout', self.setting('REQUESTS_TIMEOUT') or self.setting('URLOPEN_TIMEOUT'))
        if self.SEND_USER_AGENT and 'User-Agent' not in kwargs['headers']:
            kwargs['headers']['User-Agent'] = self.setting('USER_AGENT') or user_agent()

        try:
            if self.SSL_PROTOCOL:
                session = SSLHttpAdapter.ssl_adapter_session(self.SSL_PROTOCOL)
                response = session.request(method, url, *args, **kwargs)
            else:
                response = request(method, url, *args, **kwargs)
        except ConnectionError as err:
            raise AuthFailed(self, str(err))
        try:
            response.raise_for_status()
        except HTTPError:
            raise Exception(response.text)
        return response
