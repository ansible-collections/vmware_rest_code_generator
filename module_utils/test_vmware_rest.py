from vmware_rest import get_subdevice_type


def test_get_subdevice_type():
    assert get_subdevice_type("http://a/{b}/b/{c}/d") == "c"
    assert get_subdevice_type("http://a/{b}/b/{c}/d/{e}") is None
    assert get_subdevice_type("http://a/{b}/b") is None
