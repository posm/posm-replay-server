def osm_oauth_pipeline(backend, user, response, *args, **kwargs):
    print('IN PIPELINE')
    print(backend, user)
