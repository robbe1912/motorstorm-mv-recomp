"""Check the RSX_VC_CACHE vertex cache: compile the production vc_upload and
vc_frame with the real attribute prepare and an authored guest memory, write
watch, uploaders and arenas; reject source mutants that drop a guard."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'

# Each removes one guard; the fixture must fail on every one.
MUTANTS = [
    ('index-span-unchecked', 'int clean = vm_clean_since(e->idx_ea, e->idx_len, e->ep_idx);', 'int clean = 1;'),
    ('vertex-spans-unchecked', 'for (u32 i = 0; clean && i < e->nspan; i++) clean = vm_clean_since(e->ea[i], e->len[i], e->ep[i]);', ''),
    ('held-vertices-unwatched', 'if (kind) {   /* held strip/fan vertices', 'if (0) {   /* held strip/fan vertices'),
    ('generation-ignored', 'e->gen == s_vca[e->arena].gen && ', ''),
    ('switch-without-drain', '        wait_for_gpu_required();\n        s_vc_last_switch = s_vc_frame;\n', '        s_vc_last_switch = s_vc_frame;\n'),
    ('switch-with-records-pending', ' && s_d3d.draw_count == 0) {', ') {'),
    ('switch-unthrottled', ' && s_vc_frame - s_vc_last_switch >= VC_SWITCH_GAP', ''),
    ('cursor-not-restored', '            if (kind) s_vc_io.cursor = e->cur_out;\n', ''),
    ('constants-not-keyed', '    memcpy(st.c, b.constants, sizeof st.c);\n', ''),
    ('room-unchecked', 'if (at + need > s_vca_bytes)', 'if (0)'),
    ('verify-into-ring', 's_vc_io.dst = scratch; s_vc_io.room = vneed;', ''),
    ('verify-never-compares', 'n != e->out || memcmp(scratch,', 'n != e->out && memcmp(scratch,'),
]


def function(text, signature, after=0):
    start = text.index(signature, after)
    return text[start:text.index('\n}\n', start) + 3]


def source_checks(text):
    """The parts the fixture does not compile: replay binding, merge, records."""
    render = text[text.index('static void render_frame(void)'):]
    assert 'if (dr->vb_buf) vc_arena_view(dr->vb_buf - 1, &want_loc, &want_size);' in render, 'replay binds a cached record\'s arena'
    assert 'dr->vb_stride != bound_vb_stride || want_loc != vbv.BufferLocation' in render, 'replay rebinds on a buffer change'
    merge = function(text, 'static int vp_triangle_can_merge(')
    assert 'pv->vb_buf == buf' in merge, 'a merge never spans two buffers'
    indexed = function(text, 'static void d3d12_draw_indexed(')
    assert 'const int bypass = vc_cont && s_d3d.draws[s_d3d.draw_count - 1].vb_buf == 0;' in indexed, 'ring continuations stay in the ring'
    assert indexed.index('vp_triangle_can_merge(primitive, first, rec, rec_buf, 0, 1)') < indexed.index('vc_reemit_run(first, count)'), 'merge before re-emit'
    assert 'dr->vb_byte_offset = rec; dr->vb_buf = rec_buf;' in indexed, 'indexed records carry their buffer'
    assert text.count('dr->vb_byte_offset = rec; dr->vb_buf = 0;') == 2, 'array records name the ring'
    present = text.index('rsx_fps_stats_on_present();')
    assert text.index('vc_frame();', present) - present < 64, 'arena switch at the counted present'


def build_run(out, name, text, env):
    t = text.replace('\r\n', '\n')
    first = t.index('enum { VC_N')
    decls = t[first:t.index('static void vc_arena_view(', first)]
    template = (ROOT / 'scripts/fixtures/rsx_vertex_cache.c.in').read_text(encoding='utf-8')
    c = template.replace('@VC_DECLS@', decls).replace('@VC_FRAME@', function(t, 'static void vc_frame(void)\n{', first)) \
        .replace('@VC_RING@', function(t, 'static u32 vc_ring(', first)).replace('@VC_UPLOAD@', function(t, 'static u32 vc_upload(', first))
    d = out / name
    d.mkdir()
    src, exe = d / 'check.c', d / ('check.exe' if os.name == 'nt' else 'check')
    src.write_text(c, encoding='utf-8')
    fetch = VIDEO / 'rsx_vertex_fetch.c'
    include = ROOT / 'vendor/ps3recomp/include'
    if os.name == 'nt' and not os.environ.get('CC'):
        cmd = [env['MV_CLANG'], '/nologo', '/O1', '/I' + str(include), '/I' + str(VIDEO), str(src), str(fetch),
               '/Fe' + str(exe), '/Fo' + str(d) + os.sep]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-O1', '-I' + str(include), '-I' + str(VIDEO), '-o', str(exe), str(src), str(fetch), '-lm']
    with (d / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if build.returncode:
        return dict(name=name, build=build.returncode, log=(d / 'build.log').read_text(encoding='utf-8', errors='replace')[-3000:])
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    return dict(name=name, build=0, run=run.returncode, out=(run.stdout + run.stderr).strip()[-600:],
                exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=VIDEO / 'rsx_d3d12_backend.c')
    args = parser.parse_args()
    text = args.source.resolve().read_text(encoding='utf-8')
    source_checks(text.replace('\r\n', '\n'))
    env = os.environ.copy()
    if os.name == 'nt' and not env.get('CC'):
        from project import build_environment
        env = build_environment()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-vertex-cache-' + stamp)
    out.mkdir(parents=True)
    results = [build_run(out, 'current', text, env)]
    ok = results[0].get('build') == 0 and results[0].get('run') == 0
    print(('PASS ' if ok else 'FAIL ') + 'current: ' + (results[0].get('out') or results[0].get('log', '')))
    t = text.replace('\r\n', '\n')
    for name, old, new in MUTANTS:
        if t.count(old) != 1:
            print(f'FAIL mutant {name}: anchor found {t.count(old)} times'); ok = False; continue
        r = build_run(out, name, t.replace(old, new), env)
        results.append(r)
        caught = r.get('build') == 0 and r.get('run') != 0
        print(f"{'mutant' if caught else 'FAIL mutant'} {name} {'caught' if caught else 'NOT caught'}: {r.get('out', r.get('log', ''))[-160:]}")
        ok = ok and caught
    inputs = [args.source.resolve(), ROOT / 'scripts/fixtures/rsx_vertex_cache.c.in', VIDEO / 'rsx_vertex_fetch.c',
              VIDEO / 'rsx_vertex_fetch.h', VIDEO / 'rsx_index_strip.h', VIDEO / 'rsx_vp_layout.h', Path(__file__)]
    (out / 'result.json').write_text(json.dumps(dict(ok=ok, game_inputs=False, results=results,
        source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}), indent=2), encoding='utf-8')
    print('Evidence:', out)
    if not ok:
        sys.exit(1)
    print('PASS: production vertex cache contract and', len(MUTANTS), 'mutants rejected')


if __name__ == '__main__':
    main()
