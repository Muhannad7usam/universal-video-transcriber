from cmd_app.commands import build_parser

def test_cli_parser():
    a=build_parser().parse_args(["https://example.com/v","--video","3"])
    assert a.video==3
    b=build_parser().parse_args(["https://example.com/p","--range","2","5"])
    assert b.range_==[2,5]
