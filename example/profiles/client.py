from restorm.clients.jsonclient import JSONClient


class ApiAuthJSONClient(JSONClient):
    api_credentials = {
        'ApiAuth_ApiUser': 'automation',
        'ApiAuth-ApiKey': 'test',
    }

    def request(
            self, uri, method='GET', body=None, headers=None, redirections=5,
            connection_type=None):
        if headers is None:
            headers = {}
        headers.update(self.api_credentials)
        return super(ApiAuthJSONClient, self).request(
            uri, method, body, headers, redirections, connection_type)


profiles_client = ApiAuthJSONClient(
    root_uri='http://localhost:8080/api/v1/')
