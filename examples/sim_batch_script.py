from __future__ import annotations



from pathlib import Path



from automation import BatchScript, CaseOption, ParamCaseMatrix, ParamText

from plugins.sim_run import SimRunScript



_CASE_OPTIONS = (

    CaseOption("sanity_smoke", "Sanity Smoke", default_runs=1, default_enabled=True),

    CaseOption("nightly_regression", "Nightly Regression", default_runs=2),

    CaseOption("corner_reset", "Corner Reset", default_runs=1),

)



_DEFAULT_WORK_DIR = Path(__file__).resolve().parents[1]





class SimBatchScript(BatchScript):

    """批量仿真：勾选多个 case，每个可设运行次数，共用 seed 等参数。"""



    def build_param_schema(self):

        return [

            ParamText(name="seed", label="随机种子", default="42"),

            ParamText(name="project", label="项目", default="chip_a"),

            ParamText(name="module", label="模块", default="tb_top"),

            ParamText(name="work_dir", label="工作目录", default=str(_DEFAULT_WORK_DIR)),

            ParamText(

                name="command",

                label="命令模板",

                default="echo batch {project} {case} SEED={seed}",

            ),

            ParamText(name="pass_regex", label="PASS 正则", default=r"PASS|passed"),

            ParamText(name="fail_regex", label="FAIL 正则", default=r"FAIL"),

            ParamText(name="log_path", label="日志路径", default="sim.log"),

            ParamCaseMatrix(name="cases", label="用例", options=_CASE_OPTIONS),

        ]



    def expand_runs(self, params):

        runs: list[dict] = []

        for row in params.get("cases", []):

            if not row.get("enabled"):

                continue

            try:

                count = max(1, int(row.get("runs", 1)))

            except (TypeError, ValueError):

                count = 1

            case_id = str(row.get("id", ""))

            seed = str(params.get("seed", ""))

            for _ in range(count):

                runs.append(

                    {

                        "project": params.get("project", ""),

                        "module": params.get("module", ""),

                        "seed": seed,

                        "case": case_id,

                        "work_dir": params.get("work_dir", ""),

                        "command": params.get("command", ""),

                        "pass_regex": params.get("pass_regex", ""),

                        "fail_regex": params.get("fail_regex", ""),

                        "log_path": params.get("log_path", "sim.log"),

                        "result_status": "—",

                        "formatted_command": "",

                        "exit_code": "—",

                        "duration": "—",

                        "phase": "待运行",

                        "log_tail": "",

                        "error_message": "",

                        "error_traceback": "",

                    },

                )

        return runs



    def create_child_script(self, run_vars):

        label = run_vars.get("case", "run")

        return SimRunScript(

            name=f"仿真·{label}",

            register=False,

            **run_vars,

        )





sim_batch = SimBatchScript(name="仿真批量运行")

