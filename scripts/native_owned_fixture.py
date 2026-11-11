"""Link real owned-mode readers in isolated interpreter fixtures."""
from pathlib import Path

def write_owned_config(src: Path, out: Path):
    if not (src/'spu_native_owned.h').exists():
        return None, []
    channels=(src/'spu_channels.c').read_text()
    readers=channels[channels.index('int spu_native_owned_enabled(void)'):channels.index('void spu_native_owned_interpret(')]
    config=out/'owned-config.c'
    config.write_text('#include "spu_native_owned.h"\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n'+readers+'\nvoid spu_native_owned_interpret(spu_context* c){(void)c;fputs("unexpected owned adapter\\n",stderr);abort();}\n',encoding='utf-8')
    return config, [src/'spu_channels.c',src/'spu_native_owned.h',config,Path(__file__).resolve()]
