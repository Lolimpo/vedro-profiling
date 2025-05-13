import vedro
import vedro_httpx

import vedro_profiling


class Config(vedro.Config):

    class Plugins(vedro.Config.Plugins):

        class VedroHTTPX(vedro_httpx.VedroHTTPX):
            enabled = True

        class VedroProfiling(vedro_profiling.VedroProfiling):
            pass
