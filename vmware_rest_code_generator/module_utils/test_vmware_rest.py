from vmware_rest import get_subdevice_type, gen_args


def test_get_subdevice_type():
    assert get_subdevice_type("http://a/{b}/b/{c}/d") == "c"
    assert get_subdevice_type("http://a/{b}/b/{c}/d/{e}") is None
    assert get_subdevice_type("http://a/{b}/b") is None


def test_gen_args():
    assert gen_args({"a": [1, 2, 3]}, []) == ""
    assert gen_args({"a": [1, 2, 3]}, ["a"]) == "?a=1&a=2&a=3"
    assert gen_args({"b a f": "b c a"}, ["b a f"]) == "?b%20a%20f=b%20c%20a"
    assert gen_args({"b": False}, ["b"]) == ""
    assert gen_args({"b": None}, ["b"]) == ""
