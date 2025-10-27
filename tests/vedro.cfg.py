import vedro

import vedro_profiling


class Config(vedro.Config):
    class Plugins(vedro.Config.Plugins):
        class VedroProfiling(vedro_profiling.VedroProfiling):
            docker_compose_project_name = 'guide'
