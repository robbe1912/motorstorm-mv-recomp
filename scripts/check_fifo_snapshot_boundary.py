#!/usr/bin/env python3
"""Actual boundary protocol with authored walker outcomes, not GPU/decoder proof."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

if os.name == "nt":
    from project import build_environment

    os.environ.update(build_environment())

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "vendor/ps3recomp"
OUT = ROOT / "temp/checks" / ("fifo-boundary-" + str(time.time_ns()))
OUT.mkdir(parents=True)
source = RUNTIME / "libs/video/cellGcmSys.c"
text = source.read_text()
start = text.index("int cellGcm_with_fifo_boundary(")
end = text.index("\n}\n", start) + 3
body = text[start:end]
assert re.search(
    r"put = vm_read32.*?atomic_thread_fence\(memory_order_acquire\);.*?get = vm_read32",
    body,
    re.S,
)
fixture = r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <mutex>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <crtdbg.h>
#endif
#include "rsx_fifo_boundary.h"
using u32=uint32_t;
using std::atomic_thread_fence;using std::memory_order_acquire;
static std::mutex s_gcm_fifo_lock;
static thread_local int lock_depth;
static void AcquireSRWLockExclusive(std::mutex* m){m->lock();assert(!lock_depth);++lock_depth;}
static void ReleaseSRWLockExclusive(std::mutex* m){assert(lock_depth==1);--lock_depth;m->unlock();}
static u32 s_gcm_context_ea,s_gcm_syscall_mode;
#define GCM_CONTROL_GUEST_ADDR 0x1000
static std::atomic<u32> put,get;
static int outcome,drains,calls;
static std::atomic<int> concurrent_calls;
static u32 vm_read32(u32 ea){assert(lock_depth==1);assert(ea==0x1000||ea==0x1004);return ea==0x1000?put.load():get.load();}
static void gcm_rsx_process_fifo_unlocked(){assert(lock_depth==1);++drains;if(outcome!=1)get.store(put.load());if(outcome==2)put.fetch_add(4);}
// PRODUCTION
static int sample(void* value){assert(lock_depth==1);assert(get==put);++calls;return *static_cast<int*>(value);}
static int concurrent_sample(void*){assert(lock_depth==1);assert(get==put);++concurrent_calls;return 1;}
int main(){
#ifdef _WIN32
 _set_error_mode(_OUT_TO_STDERR);_CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);_CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
 int value=17;put=20;get=0;assert(!cellGcm_with_fifo_boundary(nullptr,&value));assert(drains==0);
 assert(!cellGcm_with_fifo_boundary(sample,&value));assert(drains==0&&calls==0);
 for(int initialized=1;initialized<=3;initialized++){
  s_gcm_context_ea=initialized&1;s_gcm_syscall_mode=initialized&2;
  for(int mode=0;mode<3;mode++){
   outcome=mode;put=20;get=0;int previous_calls=calls,previous_drains=drains;
   int result=cellGcm_with_fifo_boundary(sample,&value);assert(drains==previous_drains+1);assert(lock_depth==0);
   assert(result==(mode==0?17:0));assert(calls==previous_calls+(mode==0));
  }
 }
 outcome=0;s_gcm_context_ea=1;s_gcm_syscall_mode=0;value=-2;assert(cellGcm_with_fifo_boundary(sample,&value)==-2);
 std::vector<std::thread> threads;for(int i=0;i<4;i++)threads.emplace_back([]{for(int n=0;n<512;n++)assert(cellGcm_with_fifo_boundary(concurrent_sample,nullptr)==1);});for(auto& t:threads)t.join();assert(concurrent_calls==2048);
}
"""
receipt = dict(
    qualification=__doc__,
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    header_sha256=hashlib.sha256(
        (RUNTIME / "libs/video/rsx_fifo_boundary.h").read_bytes()
    ).hexdigest(),
    commands=[],
    results=[],
)


def run(command):
    p = subprocess.run(
        list(map(str, command)), text=True, capture_output=True, timeout=60
    )
    receipt["commands"].append(list(map(str, command)))
    receipt["results"].append(
        dict(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    )
    (OUT / "result.json").write_text(json.dumps(receipt, indent=2))
    return p


mutants = {
    "no-idle-check": body.replace(
        "if (get == put) result = handler(opaque);", "result = handler(opaque);"
    ),
    "no-drain": body.replace("gcm_rsx_process_fifo_unlocked();", ""),
    "release-before-callback": body.replace(
        "if (get == put) result = handler(opaque);",
        "if (get == put) { ReleaseSRWLockExclusive(&s_gcm_fifo_lock); result = handler(opaque); AcquireSRWLockExclusive(&s_gcm_fifo_lock); }",
    ),
    "no-initialization-check": body.replace(
        "if (s_gcm_context_ea || s_gcm_syscall_mode)", "if (1)"
    ),
}
for name, code in [("production", body), *mutants.items()]:
    assert name == "production" or code != body
    path = OUT / (name + ".cpp")
    path.write_text(fixture.replace("// PRODUCTION", code))
    exe = OUT / (name + (".exe" if os.name == "nt" else ""))
    compiler = os.environ.get("MV_CLANG") or shutil.which(
        "clang-cl" if os.name == "nt" else "c++"
    )
    assert compiler
    command = (
        [
            compiler,
            "/nologo",
            "/std:c++20",
            "/O2",
            "/MDd",
            "/UNDEBUG",
            "/EHsc",
            "/I" + str(RUNTIME / "libs/video"),
            path,
            "/Fe" + str(exe),
            "/Fo" + str(OUT / (name + ".obj")),
        ]
        if os.name == "nt"
        else [
            compiler,
            "-std=c++20",
            "-O2",
            "-UNDEBUG",
            "-pthread",
            "-I" + str(RUNTIME / "libs/video"),
            path,
            "-o",
            exe,
        ]
    )
    assert run(command).returncode == 0, OUT / "result.json"
    result = run([exe])
    assert (result.returncode == 0) == (name == "production"), (
        name,
        OUT / "result.json",
    )
receipt["passed"] = True
(OUT / "result.json").write_text(json.dumps(receipt, indent=2))
print(
    "PASS actual FIFO boundary: incomplete/new publication/init/held callback/concurrent callers, four mutants;",
    OUT,
)
