from .maker_checker_judge import run_demo

if __name__ == "__main__":
    import json
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
