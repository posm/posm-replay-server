from replay_tool.utils.osmium_handlers import AOIHandler


def test_aoi_handler():
    aoihandler = AOIHandler()
    aoihandler.apply_file('osm_test_data/osm.osm')
    # TODO: complete this
