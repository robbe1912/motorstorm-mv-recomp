"""Check the CPU deformation buffer (#346): its switches, the read paths it owns and the sampler path of the game.

The runtime fixture compiles the production switch code, the record lookup and the two public read functions next to
a model of the backend names. The query fixture compiles the production read block of deformation_query.cpp with the
production depth sampler and authored read services. Text checks hold the switch wiring of the backend and of the
game. The vendor backend compiles syntax-only on Windows. Mutants of the production text must fail."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = "libs/video/"
BACKEND, CPU_SURFACE, DEFORM, HEADER = (RUNTIME + name for name in (
    "rsx_d3d12_backend.c", "rsx_cpu_surface.inc", "rsx_deform_surface.inc", "rsx_deform_surface.h"))
QUERY = "src/motorstorm/deformation_query.cpp"

LIMITS = "#ifndef RSX_DEFORM_TARGETS_MAX"
PIXEL = "/* ---- the pixel operation of a paint draw (section B)"
CAPTURE = " * A. Capture: the inputs of the paint draws."
RECORD = "/* RSX_DEFORM_DUMP: one painted texel"
RECORD_GET = "/* Renderer thread. The record of the target of dr."
SAMPLE = "int rsx_deform_sample(uint32_t address, const uint32_t offsets[4], unsigned char out[4])"
WHEEL_STATICS = "static _Atomic u64 s_deform_wheel_frame, s_deform_wheel_frames;"
WHEEL = "void rsx_deform_wheel_log(uint32_t address, uint32_t offset, const char* level,"
DEFORM_INIT = "static void rsx_deform_init(void)"
BATCH = "static void rsx_deform_batch_end(void)"
BLOCK_START = "    patch = {{}, plan.x_fraction, plan.y_fraction};"
BLOCK_END = "    result = motorstorm::game::sample_deformation_depth(patch, mode);"
CPU_BRANCH = "    if (deform == 1 && cpu_count == 4) {"
ELSE_BRANCH = "    } else {"
TRUE_SIZE = "if (!rsx_deform_true_size(raw) && (!w || w > 2048 || !h || h > 2048)) { w = 0; h = 0; }"
OWNED = "s_cpu_surface_deform.owned&&s_cpu_surface_deform.owned(r->off)"
PROTOTYPES = (
    r"int\s+rsx_deform_mode\s*\(\s*void\s*\)\s*;",
    r"int\s+rsx_deform_sample\s*\(\s*uint32_t\s+\w+\s*,\s*const\s+uint32_t\s+\w+\s*\[\s*4\s*\]\s*,\s*unsigned\s+char\s+\w+\s*\[\s*4\s*\]\s*\)\s*;",
    r"void\s+rsx_deform_wheel_log\s*\(\s*uint32_t\s+\w+\s*,\s*uint32_t\s+\w+\s*,\s*const\s+char\s*\*\s*\w+\s*,\s*"
    r"const\s+unsigned\s+char\s+\w+\s*\[\s*4\s*\]\s*,\s*const\s+unsigned\s+char\s+\w+\s*\[\s*4\s*\]\s*\)\s*;",
)


def function(source, start):
    """One production function, from its definition to its closing brace. A
    declaration that ends with a semicolon is not the definition."""
    first, brace = source.find(start), -1
    while first >= 0:
        brace, semi = source.find("{", first), source.find(";", first)
        if semi < 0 or 0 <= brace < semi:
            break
        first = source.find(start, first + len(start))
    assert first >= 0 and brace >= 0, "missing production function " + start
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[first:end]


def block(query):
    """The read block of the production query: from the patch to the result."""
    assert query.count(BLOCK_START) == 1 and query.count(BLOCK_END) == 1, "the read block of the query moved"
    return query[query.index(BLOCK_START):query.index(BLOCK_END) + len(BLOCK_END)]


def wiring(backend, cpu, deform, header, query):
    """Order and hooks that the models cannot run. Each assertion names the rule."""
    assert backend.count('#include "rsx_deform_surface.inc"') == 1, "one include of the deform file"
    assert backend.index('#include "rsx_cpu_surface.inc"') < backend.index('#include "rsx_deform_surface.inc"'), \
        "the deform file follows rsx_cpu_surface.inc, whose names it uses"
    sites = ([(m.start(), "cpu") for m in re.finditer(r"cpu_surface_capture\(dr\);", backend)]
             + [(m.start(), "deform") for m in re.finditer(r"rsx_deform_capture\(dr, ", backend)])
    assert [kind for _, kind in sorted(sites)] == ["cpu", "deform"] * 4, \
        "each of the four record sites calls rsx_deform_capture after cpu_surface_capture"
    assert re.search(r"cpu_surface_init\(\);\s*rsx_deform_init\(\);", backend), "rsx_deform_init runs after cpu_surface_init"
    assert re.search(r"cpu_surface_frame_complete\(\);\s*rsx_deform_batch_end\(\);", backend), \
        "rsx_deform_batch_end runs after cpu_surface_frame_complete"
    assert TRUE_SIZE in function(backend, "static u32 current_rt_off("), \
        "only a target of the buffer keeps a clip size above 2048"
    expected = {
        "cpu_surface_fast_request": "if(s_cpu_surface_deform.serve&&s_cpu_surface_deform.serve(address,bytes))return 1;",
        "cpu_surface_read": "if(s_cpu_surface_deform.serve&&s_cpu_surface_deform.serve(address,bytes))return;",
        "cpu_surface_pending_add": "if(s_cpu_surface_deform.serve&&s_cpu_surface_deform.serve(address,(u32)((u64)pitch*height)))return;",
        "cpu_surface_view_update": OWNED, "cpu_surface_copy": OWNED, "cpu_surface_snapshot": OWNED,
        "cpu_surface_snapshot_clear": "if(s_cpu_surface_deform.sequence)sequences+=s_cpu_surface_deform.sequence();",
    }
    for name, text in expected.items():
        start = ("static int " if name in ("cpu_surface_fast_request", "cpu_surface_snapshot", "cpu_surface_snapshot_clear")
                 else "static void ") + name + "("
        assert text in function(cpu, start), name + " asks the deform hooks"
    init = function(deform, DEFORM_INIT)
    for hook in ("serve = rsx_deform_serve_range;", "owned = rsx_deform_owned;", "sequence = rsx_deform_sequence;"):
        assert "s_cpu_surface_deform." + hook in init, "rsx_deform_init installs " + hook
    assert "deform_shadow_compare(&s_deform_surface[i])" in function(deform, BATCH), "the batch hook compares each target"
    assert "static RsxDeformConfig s_deform = { -1, 0, { 0 }, 0, 0, 0, 0, 0, 0, 300, 0 };" in deform, \
        "every switch is off by default"
    for prototype in PROTOTYPES:
        assert re.search(prototype, header), "missing prototype " + prototype
    assert query.count('#include "rsx_deform_surface.h"') == 1, "the query includes the public header"
    text = block(query)
    assert text.count(CPU_BRANCH) == 1 and text.count(ELSE_BRANCH) == 1, "the query has one CPU branch"
    cpu_branch = text[text.index(CPU_BRANCH):text.index(ELSE_BRANCH)]
    rest = text[text.index(ELSE_BRANCH):]
    assert text.index("rsx_deform_sample(") < text.index("vm_read_snapshot("), "the query asks the CPU buffer first"
    assert "vm_read_snapshot(" not in cpu_branch and "patch.samples[index] = cpu[index];" in cpu_branch, \
        "the CPU branch reads no GPU surface"
    assert rest.index("vm_read_snapshot(") < rest.index("vm_read8(") < rest.index("rsx_deform_wheel_log("), \
        "the other branch reads the GPU, with the scalar fallback, and logs after the read"
    assert query.count("report(true, snapshot, from_cpu);") == 1 and query.count("++counts.cpu;") == 1, \
        "the query counts the reads it serves from the CPU buffer"


RUNTIME_FIXTURE = r'''/* Model of the backend names for the switches and the read paths of the CPU
 * deformation buffer. The production text follows the marker. */
#include <math.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;

#include "rsx_deform_surface.h"

uint8_t* vm_base;
static struct { u64 frame_count; } s_d3d;
static char log_text[8192];
static int test_fprintf(FILE* file, const char* format, ...);
#define fprintf test_fprintf
/* PRODUCTION */
#undef fprintf

static int test_fprintf(FILE* file, const char* format, ...)
{
    size_t used = strlen(log_text);
    va_list args;
    va_start(args, format);
    int count = vsnprintf(log_text + used, sizeof log_text - used, format, args);
    va_end(args);
    (void)file;
    return count;
}

enum { BASE = 0x100000, PITCH = 64, ROWS = 32, MIP = BASE + PITCH * ROWS };
static unsigned char memory[BASE + PITCH * ROWS + 256];
static unsigned char private_image[PITCH * ROWS], private_mip[PITCH / 2];

#define CHECK(...) \
    do { if (!(__VA_ARGS__)) { printf("FAIL %d: %s\n", __LINE__, #__VA_ARGS__); return 1; } } while (0)

static void set_switch(const char* name, const char* value)
{
#ifdef _WIN32
    _putenv_s(name, value);
#else
    setenv(name, value, 1);
#endif
}

/* Reads the switches again. An empty value removes the switch. */
static void configure(const char* targets, const char* buffer, const char* shadow, const char* capture)
{
    set_switch("RSX_DEFORM_TARGETS", targets);
    set_switch("RSX_DEFORM_BUFFER", buffer);
    set_switch("RSX_DEFORM_SHADOW", shadow);
    set_switch("RSX_DEFORM_CAPTURE", capture);
    set_switch("RSX_DEFORM_LOG", "3");
    memset(&s_deform, 0, sizeof s_deform);
    s_deform.config_state = -1;
    s_deform.log_frames = 300;
    memset(s_deform_surface, 0, sizeof s_deform_surface);
    log_text[0] = 0;
    s_d3d.frame_count = 7;
}

/* A published record of the listed target: 64 x 32 texels, then row 0 of
 * level 1 with 32 texels. */
static RsxDeformSurface* bind(void)
{
    RsxDeformSurface* s = &s_deform_surface[0];
    s->offset = 0x00A80500;
    s->guest_address = BASE;
    s->pitch = PITCH;
    s->width = PITCH;
    s->height = ROWS;
    s->mip_address = MIP;
    s->mip_width = PITCH / 2;
    atomic_store(&s->sequence, 2);
    return s;
}

int main(void)
{
    unsigned char out[4] = { 9, 9, 9, 9 };
    const unsigned char other[4] = { 1, 2, 3, 4 };
    const uint32_t offsets[4] = { 0, 1, PITCH, PITCH + 1 };
    const uint32_t bottom[4] = { (ROWS - 1) * PITCH, (ROWS - 1) * PITCH + 1, ROWS * PITCH, ROWS * PITCH + 1 };
    vm_base = memory;
    for (size_t i = 0; i < sizeof memory; i++) memory[i] = (unsigned char)(i * 7 + 3);

    /* Every switch off: no read path changes. */
    configure("", "", "", "");
    bind();
    CHECK(deform_on() == 0 && rsx_deform_mode() == 0);
    CHECK(rsx_deform_serve_range(BASE, 4) == 0 && rsx_deform_owned(0x00A80500) == 0);
    CHECK(rsx_deform_true_size(0x00A80500) == 0 && rsx_deform_sequence() == 0);
    CHECK(rsx_deform_sample(BASE, offsets, out) == 0 && out[0] == 9);
    rsx_deform_wheel_log(BASE, 0, "point", out, other);
    CHECK(log_text[0] == 0);
    printf("PASS switches off: the read paths are as they were\n");

    /* A listed target with the capture only, or a buffer switch of "0", or the
     * shadow switch without the buffer. */
    configure("00A80500", "", "", "1");
    CHECK(deform_on() == 1 && rsx_deform_true_size(0x00A80500) == 0 && rsx_deform_mode() == 0);
    configure("00A80500", "0", "1", "");
    CHECK(rsx_deform_mode() == 0 && rsx_deform_true_size(0x00A80500) == 0);
    printf("PASS capture only: no buffer, no shadow\n");

    /* The mode on: the reads take their bytes from the CPU buffer. */
    configure("00A80500", "1", "", "");
    CHECK(deform_on() == 1 && rsx_deform_mode() == 1);
    RsxDeformSurface* s = bind();
    CHECK(rsx_deform_true_size(0x00A80500) == 1 && rsx_deform_true_size(0x01A80500) == 0);
    CHECK(rsx_deform_owned(0x00A80500) == 1 && rsx_deform_owned(0x01A80500) == 0);
    CHECK(rsx_deform_serve_range(BASE, 4) == 1 && rsx_deform_serve_range(MIP, 32) == 1);
    CHECK(rsx_deform_serve_range(BASE - 1, 2) == 0 && rsx_deform_serve_range(MIP + 32, 1) == 0);
    CHECK(rsx_deform_serve_range(BASE + (ROWS - 1) * PITCH, PITCH + 1) == 0);
    CHECK(rsx_deform_sequence() == 2);
    CHECK(rsx_deform_sample(BASE, offsets, out) == 4);
    CHECK(out[0] == memory[BASE] && out[1] == memory[BASE + 1]);
    CHECK(out[2] == memory[BASE + PITCH] && out[3] == memory[BASE + PITCH + 1]);
    CHECK(rsx_deform_sample(BASE, bottom, out) == 4);
    CHECK(out[2] == memory[MIP] && out[3] == memory[MIP + 1]);
    CHECK(rsx_deform_sample(BASE + 1, offsets, out) == 0);
    atomic_store(&s->sequence, 3);
    CHECK(rsx_deform_serve_range(BASE, 4) == 0 && rsx_deform_owned(0x00A80500) == 1);
    out[0] = 9;
    CHECK(rsx_deform_sample(BASE, offsets, out) == 0 && out[0] == 9);
    atomic_store(&s->sequence, 4);
    rsx_deform_wheel_log(BASE, 0, "point", out, other);
    CHECK(log_text[0] == 0);
    printf("PASS mode on: level 0 and row 0 of level 1 served, a changing record not served, no wheel line\n");

    /* The shadow mode: the game reads the GPU bytes, the sample reads the
     * private copy, and the wheel line stops after RSX_DEFORM_LOG frames. */
    configure("00A80500", "1", "1", "");
    CHECK(rsx_deform_mode() == 2);
    s = bind();
    memset(private_image, 0x5A, sizeof private_image);
    memset(private_mip, 0xC3, sizeof private_mip);
    for (int k = 0; k < RSX_DEFORM_OP_COUNT; k++) s->ops[k] = private_image;
    s->mip = private_mip;
    CHECK(rsx_deform_serve_range(BASE, 4) == 0 && rsx_deform_owned(0x00A80500) == 0);
    CHECK(rsx_deform_sequence() == 0 && rsx_deform_true_size(0x00A80500) == 1);
    CHECK(rsx_deform_sample(BASE, bottom, out) == 4);
    CHECK(out[0] == 0x5A && out[1] == 0x5A && out[2] == 0xC3 && out[3] == 0xC3);
    for (u64 frame = 0; frame < 6; frame++) {
        s_d3d.frame_count = 10 + frame;
        for (int read = 0; read < 5; read++) rsx_deform_wheel_log(BASE, 3 * PITCH + 5, "bilinear", out, other);
    }
    CHECK(strstr(log_text, "[DEFORM_WHEEL] frame=10 x=5 y=3 level=bilinear cpu=5A5AC3C3 gpu=01020304\n") == log_text);
    int lines = 0;
    for (const char* p = log_text; (p = strchr(p, '\n')) != NULL; p++) lines++;
    CHECK(lines == 15);
    printf("PASS shadow mode: GPU read paths kept, private copy sampled, wheel line bounded\n");
    return 0;
}
'''

QUERY_FIXTURE = r'''/* Model of the read services for the production read block of the game. The
 * production block and the production depth sampler give the result. */
#include "deformation_depth.h"
#include "ps3emu/guest_read_sync.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include <stdexcept>

/* The services of the runtime. Their models follow below. */
int rsx_deform_mode();
int rsx_deform_sample(std::uint32_t, const std::uint32_t[4], unsigned char[4]);
std::uint8_t vm_read8(std::uint64_t);
void rsx_deform_wheel_log(std::uint32_t address, std::uint32_t offset, const char *level,
                          const unsigned char cpu[4], const unsigned char gpu[4]);

namespace {
constexpr std::uint32_t BASE = 0x1000u;
int buffer_mode, sample_count, snapshot_status, snapshot_calls, scalar_calls;
std::string wheel, order;
const unsigned char cpu_bytes[4] = {0xA1, 0xA2, 0xA3, 0xA4};

unsigned char gpu_byte(std::uint32_t address) {
  return static_cast<unsigned char>(((address - BASE) * 17u + 0x11u) & 0xFFu);
}

std::string hex4(const unsigned char *bytes) {
  char text[9];
  std::snprintf(text, sizeof text, "%02x%02x%02x%02x", bytes[0], bytes[1], bytes[2], bytes[3]);
  return text;
}

struct Outcome {
  float result;
  bool from_cpu, snapshot;
  int snapshot_calls, scalar_calls;
  std::string wheel, order;
};

Outcome run(int mode_value, int count, int status,
            motorstorm::game::DepthSampleMode sample_mode) {
  buffer_mode = mode_value;
  sample_count = count;
  snapshot_status = status;
  snapshot_calls = scalar_calls = 0;
  wheel.clear();
  order.clear();
  motorstorm::game::DepthPatch patch{};
  motorstorm::game::DepthSampleMode mode = sample_mode;
  motorstorm::game::DeformationDepthPlan plan{};
  plan.byte_offsets = {0, 1, 64, 65};
  plan.x_fraction = plan.y_fraction = 0.25f;
  std::uint32_t base = BASE;
  VmReadSnapshotRange ranges[4]{};
  for (unsigned index = 0; index != 4; ++index)
    ranges[index] = {base + static_cast<std::uint32_t>(plan.byte_offsets[index]), 1,
                     index};
  double result = 0.0;
  bool snapshot = false, from_cpu = false;
/* PRODUCTION_BLOCK */
  return {static_cast<float>(result), from_cpu, snapshot, snapshot_calls,
          scalar_calls, wheel, order};
}

float depth_of(const unsigned char *bytes, motorstorm::game::DepthSampleMode sample_mode) {
  motorstorm::game::DepthPatch patch{{bytes[0], bytes[1], bytes[2], bytes[3]}, 0.25f, 0.25f};
  return motorstorm::game::sample_deformation_depth(patch, sample_mode);
}
} // namespace

int rsx_deform_mode() { return buffer_mode; }

int rsx_deform_sample(std::uint32_t, const std::uint32_t[4], unsigned char out[4]) {
  if (!sample_count)
    return sample_count;
  for (int index = 0; index < sample_count; ++index)
    out[index] = cpu_bytes[index];
  return sample_count;
}

extern "C" int vm_read_snapshot(const VmReadSnapshotRange *ranges, std::uint32_t count,
                                void *destination, std::uint32_t) {
  ++snapshot_calls;
  if (snapshot_status != VM_READ_SNAPSHOT_OK)
    return snapshot_status;
  auto *out = static_cast<unsigned char *>(destination);
  for (std::uint32_t index = 0; index < count; ++index)
    out[ranges[index].output_offset] = gpu_byte(ranges[index].address);
  return VM_READ_SNAPSHOT_OK;
}

std::uint8_t vm_read8(std::uint64_t address) {
  const std::uint64_t index = address - BASE;
  order += index == 0 ? "0" : index == 1 ? "1" : index == 64 ? "2" : "3";
  ++scalar_calls;
  return gpu_byte(static_cast<std::uint32_t>(address));
}

void rsx_deform_wheel_log(std::uint32_t address, std::uint32_t offset, const char *level,
                          const unsigned char cpu[4], const unsigned char gpu[4]) {
  char text[160];
  std::snprintf(text, sizeof text,
                "[DEFORM_WHEEL] address=%08x offset=%u level=%s cpu=%s gpu=%s", address,
                offset, level, hex4(cpu).c_str(), hex4(gpu).c_str());
  wheel = text;
}

#define CHECK(condition) \
  do { \
    if (!(condition)) { \
      std::printf("FAIL %d: %s\n", __LINE__, #condition); \
      return 1; \
    } \
  } while (0)

int main() {
  using motorstorm::game::DepthSampleMode;
  const auto point = DepthSampleMode::point;
  const auto bilinear = DepthSampleMode::bilinear;
  const unsigned char gpu[4] = {gpu_byte(BASE), gpu_byte(BASE + 1), gpu_byte(BASE + 64),
                                gpu_byte(BASE + 65)};
  const auto gpu_depth = [&] { return depth_of(gpu, bilinear); };
  Outcome o;

  /* The buffer is off: the readback path gives the bytes. */
  o = run(0, 0, VM_READ_SNAPSHOT_OK, bilinear);
  CHECK(o.snapshot_calls == 1 && o.scalar_calls == 0 && !o.from_cpu && o.snapshot);
  CHECK(o.result == gpu_depth() && o.wheel.empty());
  std::printf("PASS buffer off: the readback path\n");

  /* The mode on: the CPU bytes are the result. The query reads no GPU surface. */
  o = run(1, 4, VM_READ_SNAPSHOT_OK, bilinear);
  CHECK(o.snapshot_calls == 0 && o.scalar_calls == 0 && o.from_cpu && !o.snapshot);
  CHECK(o.result == depth_of(cpu_bytes, bilinear) && o.wheel.empty());
  /* The buffer does not hold the four bytes: the readback path. */
  o = run(1, 3, VM_READ_SNAPSHOT_OK, bilinear);
  CHECK(o.snapshot_calls == 1 && !o.from_cpu && o.result == gpu_depth() && o.wheel.empty());
  std::printf("PASS mode on: the CPU bytes, or the readback path without them\n");

  /* The shadow mode: the readback path is the result, the line holds both. */
  o = run(2, 4, VM_READ_SNAPSHOT_OK, point);
  const std::string line = "[DEFORM_WHEEL] address=00001000 offset=0 level=point cpu=a1a2a3a4 gpu=";
  CHECK(o.snapshot_calls == 1 && !o.from_cpu && o.snapshot);
  CHECK(o.result == depth_of(gpu, point) && o.wheel == line + hex4(gpu));
  o = run(2, 4, VM_READ_SNAPSHOT_UNAVAILABLE, point);
  CHECK(o.scalar_calls == 4 && o.order == "0132" && !o.snapshot);
  CHECK(o.result == depth_of(gpu, point) && o.wheel == line + hex4(gpu));
  o = run(2, 4, VM_READ_SNAPSHOT_OK, bilinear);
  CHECK(o.wheel == "[DEFORM_WHEEL] address=00001000 offset=0 level=bilinear cpu=a1a2a3a4 gpu=" + hex4(gpu));
  o = run(2, 3, VM_READ_SNAPSHOT_OK, point);
  CHECK(o.snapshot_calls == 1 && o.wheel.empty());
  std::printf("PASS shadow mode: the GPU bytes are the result, the wheel line holds both\n");
  return 0;
}
'''

# (name, production text, changed text). Each changed text must fail a fixture.
RUNTIME_MUTANTS = [
    ("buffer-on-for-zero", '    return value && *value && strcmp(value, "0") != 0;', '    return value != NULL;'),
    ("buffer-on-without-switch", 's_deform.buffer = deform_switch("RSX_DEFORM_BUFFER");', "s_deform.buffer = 1;"),
    ("true-size-without-buffer", "    return deform_on() && s_deform.buffer && deform_listed(offset);",
     "    return deform_on() && deform_listed(offset);"),
    ("shadow-serves-the-gpu-path", "return deform_on() && s_deform.buffer && !s_deform.shadow;",
     "return deform_on() && s_deform.buffer;"),
    ("serve-while-changing", "if (!sequence || (sequence & 1) || !deform_surface_holds(s, address, bytes)) continue;",
     "if (!sequence || !deform_surface_holds(s, address, bytes)) continue;"),
    ("serve-below-the-base", "(u64)address >= begin && (u64)address + bytes <= end)",
     "(u64)address + bytes <= end)"),
    ("mode-reports-on-in-shadow", "return !deform_on() || !s_deform.buffer ? 0 : s_deform.shadow ? 2 : 1;",
     "return !deform_on() || !s_deform.buffer ? 0 : 1;"),
    ("shadow-sample-reads-guest", "    return s->ops[0] ? s->ops[s_deform.op] : vm_base + s->guest_address;",
     "    return vm_base + s->guest_address;"),
    ("sample-skips-mip-row",
     "            else if (at >= mip_begin && at < mip_end) out[count++] = mip[at - mip_begin];\n", ""),
    ("wheel-line-in-mode-on", "    if (rsx_deform_mode() != 2) return;", "    if (rsx_deform_mode() != 1) return;"),
    ("wheel-line-unbounded",
     "    if (atomic_load_explicit(&s_deform_wheel_frames, memory_order_relaxed) > s_deform.log_frames) return;",
     "    if (atomic_load_explicit(&s_deform_wheel_frames, memory_order_relaxed) > 1000000) return;"),
    ("first-call-reads-off", "            st = s_deform.any ? 2 : 0;\n", ""),
    ("wheel-line-swaps-x-and-y", "pitch ? offset % pitch : 0, pitch ? offset / pitch : 0,",
     "pitch ? offset / pitch : 0, pitch ? offset % pitch : 0,"),
]
QUERY_MUTANTS = [
    ("cpu-path-ignored", CPU_BRANCH, "    if (false) {"),
    ("partial-cpu-bytes-used", "deform == 1 && cpu_count == 4) {", "deform == 1) {"),
    ("cpu-bytes-copied-wrong", "patch.samples[index] = cpu[index];", "patch.samples[index] = cpu[3 - index];"),
    ("offsets-reversed", "offsets[index] = static_cast<std::uint32_t>(plan.byte_offsets[index]);",
     "offsets[index] = static_cast<std::uint32_t>(plan.byte_offsets[3 - index]);"),
    ("shadow-uses-cpu-bytes", CPU_BRANCH, "    if (deform >= 1 && cpu_count == 4) {"),
    ("wheel-line-without-cpu-bytes", "if (deform == 2 && cpu_count == 4)", "if (deform == 2 && cpu_count > 0)"),
    ("wheel-level-swapped", '                                 ? "bilinear"\n                                 : "point",',
     '                                 ? "point"\n                                 : "bilinear",'),
]
WIRING_MUTANTS = [
    ("backend-without-batch-hook", {"backend": lambda text: text.replace("    rsx_deform_batch_end();\n", "")}),
    ("batch-hook-before-frame-complete",
     {"backend": lambda text: text.replace("cpu_surface_frame_complete();\n    rsx_deform_batch_end();",
                                           "rsx_deform_batch_end();\n    cpu_surface_frame_complete();")}),
    ("backend-without-true-size", {"backend": lambda text: text.replace(TRUE_SIZE, TRUE_SIZE.replace("!rsx_deform_true_size(raw) && ", ""))}),
    ("init-without-serve-hook",
     {"deform": lambda text: text.replace("    s_cpu_surface_deform.serve = rsx_deform_serve_range;\n", "")}),
    ("copy-ignores-owned",
     {"cpu": lambda text: text.replace(function(text, "static void cpu_surface_copy("),
                                       function(text, "static void cpu_surface_copy(").replace(OWNED + ")return;", ""))}),
    ("buffer-on-by-default",
     {"deform": lambda text: text.replace("static RsxDeformConfig s_deform = { -1, 0, { 0 }, 0, 0, 0, 0, 0, 0, 300, 0 };",
                                          "static RsxDeformConfig s_deform = { -1, 0, { 0 }, 0, 0, 1, 0, 0, 0, 300, 0 };")}),
    ("header-without-sample-prototype",
     {"header": lambda text: re.sub(r"int\s+rsx_deform_sample\s*\([^;]*;\s*", "", text, flags=re.S)}),
    ("query-without-header", {"query": lambda text: text.replace('#include "rsx_deform_surface.h"\n', "")}),
    ("cpu-reads-not-counted", {"query": lambda text: text.replace("report(true, snapshot, from_cpu);", "report(true, snapshot);")}),
]


def runtime_text(deform):
    """The production text of the runtime fixture: the limits, the pixel operations with the switches, the record
    lookup, and the two public read functions."""
    for marker in (LIMITS, PIXEL, CAPTURE, RECORD, RECORD_GET, SAMPLE, WHEEL_STATICS, WHEEL):
        assert deform.count(marker) == 1, marker
    statics = deform[deform.index(WHEEL_STATICS):deform.index("\n", deform.index(WHEEL_STATICS))]
    return "\n\n".join([
        deform[deform.index(LIMITS):deform.index(PIXEL)],
        deform[deform.index(PIXEL):deform.rindex("/*", 0, deform.index(CAPTURE))],
        deform[deform.index(RECORD):deform.index(RECORD_GET)],
        statics, function(deform, SAMPLE), function(deform, WHEEL)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler")
    parser.add_argument("--vendor", type=Path, default=ROOT / "vendor/ps3recomp", help="folder of the runtime source")
    parser.add_argument("--output", type=Path, help="folder for the composed programs and result.json")
    args = parser.parse_args()
    if os.name == "nt":
        from project import build_environment

        os.environ.update(build_environment())
    vendor = args.vendor
    paths = {name: vendor / name for name in (BACKEND, CPU_SURFACE, DEFORM, HEADER)}
    paths["query"] = ROOT / QUERY
    texts = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    out = args.output or ROOT / "build/self-tests/deform-cpu-buffer"
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "qualification": "Production switch code, record lookup, public read functions and the read block of the "
                         "query with authored services. The painter and the shadow comparison run in the fork check "
                         "tests/check_rsx_deform_surface.py. The GPU comparison needs a game run.",
        "source_sha256": {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path):
                          hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()},
        "commands": [], "mutants_rejected": [], "wiring_mutants_rejected": [],
    }

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    compiler = (args.compiler or os.environ.get("MV_CLANG") or os.environ.get("CC")
                or shutil.which("clang-cl") or shutil.which("clang") or shutil.which("cc"))
    assert compiler, "No C compiler found; pass --compiler"
    msvc = Path(compiler).name.lower() in ("cl", "cl.exe", "clang-cl", "clang-cl.exe")

    def run(label, kind, text):
        """None when the composed program passes, else the reason it fails."""
        folder = out / label
        folder.mkdir(exist_ok=True)
        c = folder / ("check.c" if kind == "runtime" else "check.cpp")
        if kind == "runtime":
            text = RUNTIME_FIXTURE.replace("/* PRODUCTION */",
                                           runtime_text(texts[DEFORM]) if text is None else text)
        else:
            source = texts["query"] if text is None else text
            text = QUERY_FIXTURE.replace("/* PRODUCTION_BLOCK */", block(source))
        c.write_text(text, encoding="utf-8")
        exe = folder / ("check.exe" if os.name == "nt" else "check")
        video, include = vendor / "libs/video", vendor / "include"
        if kind == "runtime":
            if msvc:
                cmd = [compiler, "/nologo", "/O2", "/std:c11", "/experimental:c11atomics", "/clang:-std=c17",
                       "/I" + str(video), "/I" + str(include), str(c), "/Fo" + str(folder) + os.sep, "/Fe" + str(exe)]
            else:
                cmd = [compiler, "-std=c11", "-O2", "-I" + str(video), "-I" + str(include), str(c), "-o", str(exe)]
        else:
            depth = ROOT / "src/motorstorm/deformation_depth.cpp"
            if msvc:
                cmd = [compiler, "/nologo", "/std:c++20", "/O2", "/EHsc", "/W4", "/D_CRT_SECURE_NO_WARNINGS",
                       "/I" + str(include), "/I" + str(ROOT / "src/motorstorm"), str(c), str(depth),
                       "/Fo" + str(folder) + os.sep, "/Fe" + str(exe)]
            else:
                cmd = [compiler, "-std=c++20", "-O2", "-I" + str(include), "-I" + str(ROOT / "src/motorstorm"),
                       str(c), str(depth), "-o", str(exe)]
        built = subprocess.run(cmd, capture_output=True, text=True)
        (folder / "build.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        report["commands"].append({"name": label, "command": cmd, "returncode": built.returncode, "kind": "build"})
        save()
        if built.returncode:
            return "build failed: " + (built.stdout + built.stderr).strip()[-400:]
        done = subprocess.run([str(exe)], capture_output=True, text=True, timeout=300)
        (folder / "run.log").write_text(done.stdout + done.stderr, encoding="utf-8")
        report["commands"].append({"name": label, "returncode": done.returncode, "kind": "run"})
        save()
        if done.returncode:
            fails = [line for line in done.stdout.splitlines() if line.startswith("FAIL")]
            return "exit %d: %s" % (done.returncode, fails[-1] if fails else done.stderr.strip()[-200:])
        if "PASS" not in done.stdout:
            return "no PASS line"
        return None

    wiring(texts[BACKEND], texts[CPU_SURFACE], texts[DEFORM], texts[HEADER], texts["query"])
    print("PASS wiring: record sites, init, batch hook, true size, deform hooks in the read paths, "
          "switches off by default, prototypes, query order")

    actual = runtime_text(texts[DEFORM])
    failure = run("runtime", "runtime", actual)
    assert failure is None, "runtime: " + failure
    print((out / "runtime" / "run.log").read_text(encoding="utf-8").strip().replace("\n", "; "))
    for name, before, after in RUNTIME_MUTANTS:
        assert actual.count(before) == 1, name
        failure = run("mutant-runtime-" + name, "runtime", actual.replace(before, after))
        assert failure is not None, "mutant survived: " + name
        report["mutants_rejected"].append(name)
        print("PASS mutant " + name + " rejected: " + failure)

    failure = run("query", "query", None)
    assert failure is None, "query: " + failure
    print((out / "query" / "run.log").read_text(encoding="utf-8").strip().replace("\n", "; "))
    for name, before, after in QUERY_MUTANTS:
        assert texts["query"].count(before) == 1, name
        changed = texts["query"].replace(before, after)
        assert changed != texts["query"], name
        failure = run("mutant-query-" + name, "query", changed)
        assert failure is not None, "mutant survived: " + name
        report["mutants_rejected"].append(name)
        print("PASS mutant " + name + " rejected: " + failure)

    keys = {"backend": BACKEND, "cpu": CPU_SURFACE, "deform": DEFORM, "header": HEADER, "query": "query"}
    for name, changes in WIRING_MUTANTS:
        changed = {key: texts[path] for key, path in keys.items()}
        for where, change in changes.items():
            changed[where] = change(changed[where])
            assert changed[where] != texts[keys[where]], (name, where)
        try:
            wiring(changed["backend"], changed["cpu"], changed["deform"], changed["header"], changed["query"])
        except AssertionError as exc:
            report["wiring_mutants_rejected"].append(name)
            print("PASS wiring mutant " + name + " rejected: " + str(exc))
            continue
        raise AssertionError("wiring mutant survived: " + name)

    if os.name == "nt":
        includes = [vendor / part for part in ("include", "libs/video", "runtime/ppu", "runtime/spu", "runtime/memory",
                                               "runtime/syscalls", "runtime/platform")]
        cmd = [compiler, "/nologo", "/Zs", "/std:c11", "/experimental:c11atomics", "/clang:-std=c17",
               "/D_CRT_SECURE_NO_WARNINGS", "-Wno-everything", *["/I" + str(p) for p in includes],
               str(vendor / BACKEND)]
        syntax = subprocess.run(cmd, capture_output=True, text=True)
        report["commands"].append({"name": "syntax", "command": cmd, "returncode": syntax.returncode, "kind": "build"})
        save()
        assert syntax.returncode == 0, "backend syntax: " + (syntax.stdout + syntax.stderr).strip()[-400:]
        print("PASS the backend compiles syntax-only with the deform file and the header")
    else:
        print("SKIP the backend syntax check: it needs the Windows toolchain")

    save()
    report["passed"] = True
    print("PASS: CPU deformation buffer, switches, read paths and game sampler path ("
          + str(len(RUNTIME_MUTANTS)) + " runtime, " + str(len(QUERY_MUTANTS)) + " query and "
          + str(len(WIRING_MUTANTS)) + " wiring mutants rejected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
