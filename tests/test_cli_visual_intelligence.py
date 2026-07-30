from ace.cli import create_parser


def test_visual_repair_commands_parse():
    parser = create_parser()
    args = parser.parse_args(["visuals", "regenerate", "last", "--shot", "4", "--no-cloud-judge"])
    assert args.visuals_command == "regenerate"
    assert args.shot == 4
    args = parser.parse_args(["visuals", "replace", "last", "--shot", "4", "--candidate", "candidate-9", "--approve"])
    assert args.candidate == "candidate-9"
    args = parser.parse_args(["rerun", "last", "--from", "visual-plan"])
    assert args.rerun_from == "visual-plan"
