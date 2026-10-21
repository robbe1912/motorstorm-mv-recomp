#include "job_wait.h"
#include "native_job_wait_api.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <stdexcept>
#include <immintrin.h>

void motorstorm_job_marker_wait(ppu_context*);
namespace {
void check(bool value, const char* text) { if (!value) throw std::runtime_error(text); }
struct Model {
    unsigned polls=0, ordinal=0, cooperations=0;
    bool wide=false, fail=false;
    std::uint32_t owner() const { return polls < 40 ? 0x4000 : 0x5000; }
};
motorstorm::game::JobProgressStart begin(void* raw) {
    auto& m=*static_cast<Model*>(raw);
    check(m.ordinal==0 || m.ordinal==8,"Complete seven-counter scan");
    ++m.polls; m.ordinal=1;
    return {m.owner(),static_cast<std::uint16_t>(m.wide ? 0xffff : (m.polls < 70 ? 1 : 3))};
}
void barrier(void* raw) {
    auto& m=*static_cast<Model*>(raw);
    check(m.ordinal==1,"Taken/barrier/lane order"); m.ordinal=2;
}
std::uint16_t active(void* raw,std::uint32_t owner,unsigned lane) {
    auto& m=*static_cast<Model*>(raw);
    check(owner==m.owner(),"Ownership re-resolution");
    check(lane<6 && m.ordinal==2+lane,"Taken/barrier/lane order"); ++m.ordinal;
    return static_cast<std::uint16_t>(m.wide ? (lane==0 && m.polls<65 ? 0xfffe : 0xffff) :
        (lane==5 && m.polls<85 ? 2 : 3));
}
void cooperate(void* raw) {
    auto& m=*static_cast<Model*>(raw);
    check(m.ordinal==8,"Cooperation before complete scan"); ++m.cooperations;
    if(m.fail) throw std::runtime_error("Authored scheduler failure");
}
Model bridge;
unsigned original_calls=0;
bool fail_scheduler=false;
unsigned clock_calls=0;
}

bool native_job_wait_fixture_clock(std::uint64_t& tick,std::uint64_t& frequency) noexcept {
    ++clock_calls;
    const char* mode=std::getenv("MS_JOB_WAIT_FIXTURE_CLOCK");
    if(mode && ((!std::strcmp(mode,"start-fail") && clock_calls%2==1) ||
                (!std::strcmp(mode,"end-fail") && clock_calls%2==0))) return false;
    tick=1234000000000ULL+clock_calls*70;
    frequency=1000000;
    if(mode && !std::strcmp(mode,"backward")) tick=clock_calls%2 ? 200 : 100;
    if(mode && !std::strcmp(mode,"frequency")) frequency+=clock_calls;
    if(mode && !std::strcmp(mode,"zero-frequency")) frequency=0;
    return true;
}
std::uint64_t native_job_wait_fixture_thread() noexcept { return 0x334455; }

std::uint32_t vm_read32(std::uint64_t address) {
    check(address==0x1004,"List-pointer read");
    check(bridge.ordinal==0 || bridge.ordinal==8,"Bridge complete scan");
    ++bridge.polls; bridge.ordinal=1; return bridge.owner();
}
std::uint16_t vm_read16(std::uint64_t address) {
    if(address==bridge.owner()+18) {
        check(bridge.ordinal==1,"Bridge taken read"); bridge.ordinal=2;
        return bridge.polls<70 ? 1 : 3;
    }
    const auto lane=static_cast<unsigned>((address-bridge.owner()-20)/2);
    return active(&bridge,bridge.owner(),lane);
}
void native_job_wait_fixture_cooperate() {
    cooperate(&bridge);
    if(fail_scheduler) throw std::runtime_error("Authored timer failure");
}
void game_original_job_marker_wait(ppu_context*) { ++original_calls; }

int main(int argc,char** argv) {
    try {
        const auto saved_fp=_mm_getcsr();
        const auto caller_fp=(saved_fp&~0x6000u)|0x4000u|0x21u;
        _mm_setcsr(caller_fp);
        using namespace motorstorm::game;
        for (bool wide : {false,true}) {
            Model m; m.wide=wide;
            const auto result=wait_for_job_marker({&m,begin,barrier,active,cooperate},wide?0xffff:3);
            check(result.minimum==(wide?0xffff:3) && result.polls==(wide?65u:85u),"All active lanes must complete");
            check(result.owner==0x5000,"Ownership re-resolution");
            check(m.cooperations==result.polls-64 && result.cooperations==m.cooperations,"Cooperation for blocked work");
        }
        Model ready;
        const auto done=wait_for_job_marker({&ready,begin,barrier,active,cooperate},0);
        check(done.polls==1 && ready.ordinal==8 && ready.cooperations==0,"Ready fast path still scans all counters");
        Model failure; failure.fail=true;
        bool threw=false;
        try { wait_for_job_marker({&failure,begin,barrier,active,cooperate},3); }
        catch(const std::runtime_error& e) { threw=std::strcmp(e.what(),"Authored scheduler failure")==0; }
        check(threw,"Scheduler error must propagate");

        ppu_context ctx; std::memset(&ctx,0xa5,sizeof(ctx));
        ctx.gpr[3]=0x1000; ctx.gpr[4]=0xfeed000000000003ULL;
        ctx.lr=0x123456789abcdefULL;
        auto expected=ctx;
        const bool reference=argc>1 && std::strcmp(argv[1],"reference")==0;
        if(reference) {
            motorstorm_job_marker_wait(&ctx);
            check(original_calls==1 && bridge.polls==0 && !std::memcmp(&ctx,&expected,sizeof(ctx)),"Reference mode");
        } else {
            motorstorm_job_marker_wait(&ctx);
            expected.gpr[0]=expected.gpr[11]=3; expected.gpr[8]=0x5000;
            expected.gpr[9]=0x501a; expected.gpr[10]=6; expected.ctr=0;
            expected.cr=(expected.cr&~0xfu)|2u;
            check(original_calls==0 && !std::memcmp(&ctx,&expected,sizeof(ctx)),"Native return ABI");
            bridge={};ctx.gpr[4]=0;expected=ctx;
            motorstorm_job_marker_wait(&ctx);
            expected.gpr[0]=expected.gpr[11]=1;expected.gpr[8]=0x4000;
            expected.gpr[9]=0x401a;expected.cr=(expected.cr&~0xfu)|8u;
            check(original_calls==0 && !std::memcmp(&ctx,&expected,sizeof(ctx)),"Ready marker return ABI");
            bridge={}; ctx=expected; ctx.gpr[4]=0x10000; expected=ctx;
            motorstorm_job_marker_wait(&ctx);
            check(original_calls==1 && !std::memcmp(&ctx,&expected,sizeof(ctx)),"Unsupported marker fallback without writes");
            bridge={}; ctx.gpr[4]=3; expected=ctx; fail_scheduler=true;
            motorstorm_job_marker_wait(&ctx);
            check(original_calls==2 && !std::memcmp(&ctx,&expected,sizeof(ctx)),"Timer failure fallback without writes");
        }
        check(_mm_getcsr()==caller_fp,"Caller FP environment");
        const char* profiling=std::getenv("MS_NATIVE_JOB_WAIT_PROFILE");
        const bool profiled=profiling && !std::strcmp(profiling,"1");
        check(clock_calls==((profiled && !reference)?6u:0u),"Disabled/reference profiling must not read clocks");
        _mm_setcsr(saved_fp);
        std::puts("PASS native job wait: ordering, seven counters, ownership, cooperation, ABI and visible fallback");
        return 0;
    } catch(const std::exception& e) {
        std::fprintf(stderr,"FAIL: %s\n",e.what()); return 1;
    }
}
