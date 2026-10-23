#include "threshold_scan.h"
#include "spu_context.h"
#include "spu_interp.h"
#include "spu_native_leaf.h"
extern "C" int game_particle_threshold_code_matches(const spu_context*);
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <memory>
#include <stdexcept>

namespace {
using namespace motorstorm::game;
constexpr std::uint32_t begin_pc = 0x12338, end_pc = 0x12400, final_pc = 0x123fc;
enum class Mode { reference, shadow, native };
struct State {
    Mode mode = Mode::reference;
    bool policy_interpretation = std::getenv("SPU_PM_INTERP") != nullptr;
    std::atomic<std::uint64_t> completed{0}, compared{0}, fallbacks{0}, original_instructions{0};
    State() {
        const char* text = std::getenv("MS_NATIVE_PARTICLE_THRESHOLDS");
        if (!text || !std::strcmp(text,"0") || !std::strcmp(text,"reference")) {}
        else if (!std::strcmp(text,"shadow")) mode = Mode::shadow;
        else if (!std::strcmp(text,"1") || !std::strcmp(text,"native")) mode = Mode::native;
        else throw std::invalid_argument("Invalid MS_NATIVE_PARTICLE_THRESHOLDS mode");
        std::fprintf(stderr,"[native-particle-threshold] mode=%s\n",text ? text : "reference");
    }
};
State& state() { static State value; return value; }
[[noreturn]] void error(const char* reason) {
    std::fprintf(stderr,"NATIVE_PARTICLE_THRESHOLD_ERROR %s\n",reason); std::abort();
}
std::uint32_t word(const unsigned char* p) {
    return (std::uint32_t(p[0])<<24)|(std::uint32_t(p[1])<<16)|(std::uint32_t(p[2])<<8)|p[3];
}
float real(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
bool pending(const spu_context* ctx) {
    return ctx->int_enable && (__atomic_load_n(&ctx->event_status,__ATOMIC_ACQUIRE) & ctx->event_mask);
}
constexpr unsigned output_registers[] = {2,4,5,6,7,8,9,15};
struct Prepared {
    std::array<u128,8> registers;
    std::uint64_t instructions;
};
const char* prepare_inputs(const spu_context* ctx,std::uint64_t remaining,Prepared& out) {
    if (ctx->ls!=ctx->ls_store || ctx->status!=1 || ctx->irq_saved || ctx->list_stall_mask || pending(ctx))
        return "context/IRQ/DMA ownership";
    // The current MFC backend raises list-stall notify (0x2) synchronously
    // during list submission/ack on this context's owning thread. This exact
    // channel-free span cannot raise it. Other unmasked sources could arrive
    // midway through the original loop and require instruction-level delivery.
    if (ctx->int_enable && (ctx->event_mask & ~0x2u)) return "asynchronous interrupt source";
    if (!game_particle_threshold_code_matches(ctx)) return "code identity";
    // A resident-image transition inside the span needs ordinary execution.
    if (ctx->policy_mode) {
        for (const auto& span:ctx->resident_code) if (span.size) {
            const auto end=std::uint64_t(span.lsa)+span.size;
            if ((span.lsa>begin_pc && span.lsa<end_pc) || (end>begin_pc && end<end_pc))
                return "resident boundary";
        }
        if ((ctx->wi_span_lo>begin_pc && ctx->wi_span_lo<end_pc) ||
            (ctx->wi_span_hi>begin_pc && ctx->wi_span_hi<end_pc)) return "walk-in boundary";
    }
    if (!state().policy_interpretation && !(ctx->interp_span_lo<=begin_pc && ctx->interp_span_hi>=end_pc))
        return "original interpretation policy";
    const std::array<u128,5> inputs = {ctx->gpr[6],ctx->gpr[84],ctx->gpr[10],ctx->gpr[11],ctx->gpr[8]};
    const auto begin=inputs[0]._u32[0],end=inputs[1]._u32[0];
    if ((begin&3) || end<=begin || (end-begin)%32 || end>0x3ffc0 || inputs[2]._u32[0]!=44)
        return "sample extent/stride";
    const auto count=(end-begin)/4,first=((begin+44)&15)/4,used=(count+first+3)/4;
    // One back edge scans eight successive components in fifty instructions.
    // Loads rotate the packed record to expose four cyclic threshold views.
    out.instructions=std::uint64_t(end-begin)/32*50;
    if (out.instructions>remaining) return "instruction budget";
    if (used>257) return "sample capacity";
    const auto base=(begin+44)&~15u;
    std::array<unsigned char,257*16> snapshot;
    std::memcpy(snapshot.data(),ctx->ls+base,used*16);
    std::array<ThresholdRecord,257> records;
    for (unsigned r=0;r<used;++r) for (unsigned lane=0;lane<4;++lane)
        records[r].samples[lane]=real(word(snapshot.data()+r*16+lane*4));
    std::array<float,4> thresholds; ThresholdFlags flags;
    for (unsigned lane=0;lane<4;++lane) {
        thresholds[lane]=real(inputs[3]._u32[lane]); flags[lane]=inputs[4]._u32[lane];
    }
    const auto result=try_accumulate_threshold_failures(records.data(),used,first,count,thresholds,flags);
    if (!result) return "unsupported numeric range";
    flags=*result;
    const auto last=end+40,rotation=(last&15)/4;
    const auto* last_record=snapshot.data()+(last&~15u)-base;
    for (unsigned lane=0;lane<4;++lane) {
        const std::uint32_t cursor=inputs[0]._u32[lane]+(end-begin);
        out.registers[0]._u32[lane]=cursor-28;
        out.registers[1]._u32[lane]=(thresholds[lane]>real(word(last_record+((lane+rotation)%4)*4))) ? 0xffffffffu : 0;
        out.registers[2]._u32[lane]=word(last_record+lane*4);
        out.registers[3]._u32[lane]=cursor;
        out.registers[4]._u32[lane]=cursor-4+inputs[2]._u32[lane];
        out.registers[5]._u32[lane]=flags[lane];
        out.registers[6]._u32[lane]=(cursor==inputs[1]._u32[lane]) ? 0xffffffffu : 0;
        out.registers[7]._u32[lane]=1;
    }
    std::atomic_signal_fence(std::memory_order_seq_cst);
    if (std::memcmp(&inputs[0],&ctx->gpr[6],16) || std::memcmp(&inputs[1],&ctx->gpr[84],16) ||
        std::memcmp(&inputs[2],&ctx->gpr[10],16) || std::memcmp(&inputs[3],&ctx->gpr[11],16) ||
        std::memcmp(&inputs[4],&ctx->gpr[8],16) || std::memcmp(snapshot.data(),ctx->ls+base,used*16) ||
        !game_particle_threshold_code_matches(ctx) || pending(ctx)) return "input changed";
    return nullptr;
}
void commit(spu_context* ctx,const Prepared& prepared) {
    for (unsigned i=0;i<8;++i) ctx->gpr[output_registers[i]]=prepared.registers[i];
    ctx->pc=end_pc;
    // The interpreter's policy walk-in bookkeeping observes the last executed
    // branch. Its next outer iteration separately observes the continuation.
    if (ctx->policy_mode) ctx->wi_prev_pc=final_pc;
}
struct Reports {
    std::uint64_t steps=g_spu_interp_steps;
    std::uint32_t pc=g_spu_interp_last_pc;
    spu_lifted_fn queued=g_spu_trampoline_fn;
    ~Reports() { g_spu_interp_steps=steps;g_spu_interp_last_pc=pc;g_spu_trampoline_fn=queued; }
};
void interpreted(spu_context* ctx,std::uint64_t count) {
    Reports restore;
    spu_interp_run_until_budget(ctx,begin_pc,end_pc,count);
    if (ctx->pc!=end_pc || g_spu_interp_steps!=count || g_spu_interp_last_pc!=final_pc)
        error("original scan continuation/count mismatch");
}
bool compare(const spu_context* ctx,const Prepared& prepared) {
    auto reference=std::make_unique<spu_context>();
    auto candidate=std::make_unique<spu_context>();
    std::atomic_signal_fence(std::memory_order_seq_cst);
    std::memcpy(reference.get(),ctx,sizeof(*ctx));
    std::atomic_signal_fence(std::memory_order_seq_cst);
    std::memcpy(candidate.get(),ctx,sizeof(*ctx));
    std::atomic_signal_fence(std::memory_order_seq_cst);
    if (std::memcmp(reference.get(),candidate.get(),sizeof(*ctx))) return false;
    reference->ls=reference->ls_store;candidate->ls=candidate->ls_store;
    commit(candidate.get(),prepared);interpreted(reference.get(),prepared.instructions);
    reference->ls=candidate->ls;
    if (std::memcmp(reference.get(),candidate.get(),sizeof(*ctx))) {
        const auto* a=reinterpret_cast<const unsigned char*>(candidate.get());
        const auto* b=reinterpret_cast<const unsigned char*>(reference.get());
        for (std::size_t i=0;i<sizeof(*ctx);++i) if(a[i]!=b[i]) {
            std::fprintf(stderr,"NATIVE_PARTICLE_THRESHOLD_DIFF byte=%zu native=%02x reference=%02x\n",i,a[i],b[i]);break;
        }
        error("original interpreter mismatch");
    }
    ++state().compared; return true;
}
struct Pending { Prepared prepared; const spu_context* owner; };
thread_local Pending prepared_leaf;
void execute(spu_context* ctx,const spu_native_leaf_plan* plan) try {
    if (plan->cookie!=&prepared_leaf || prepared_leaf.owner!=ctx) error("plan ownership mismatch");
    if (state().mode==Mode::shadow) interpreted(ctx,plan->instructions);
    else commit(ctx,prepared_leaf.prepared);
    const auto instructions=state().original_instructions.fetch_add(plan->instructions,std::memory_order_relaxed)+plan->instructions;
    const auto count=++state().completed;
    if (count==1 || count%1024==0)
        std::fprintf(stderr,"[native-particle-threshold] completed=%llu compared=%llu fallbacks=%llu instructions=%llu original_instructions_total=%llu\n",
            static_cast<unsigned long long>(count),static_cast<unsigned long long>(state().compared.load()),
            static_cast<unsigned long long>(state().fallbacks.load()),static_cast<unsigned long long>(plan->instructions),
            static_cast<unsigned long long>(instructions));
} catch (const std::exception& failure) { error(failure.what()); }
catch (...) { error("unknown execution exception"); }
int prepare(const spu_context* ctx,std::uint64_t remaining,spu_native_leaf_plan* plan) try {
    if (state().mode==Mode::reference || remaining<50) return 0;
    if (const char* reason=prepare_inputs(ctx,remaining,prepared_leaf.prepared)) {
        const auto count=++state().fallbacks;
        if (count==1 || count%1024==0)
            std::fprintf(stderr,"[native-particle-threshold] INTERPRETER fallback=%llu reason=%s\n",
                static_cast<unsigned long long>(count),reason);
        return 0;
    }
    if (state().mode==Mode::shadow && !compare(ctx,prepared_leaf.prepared)) {
        const auto count=++state().fallbacks;
        std::fprintf(stderr,"[native-particle-threshold] INTERPRETER fallback=%llu reason=shadow snapshot changed\n",
            static_cast<unsigned long long>(count));return 0;
    }
    prepared_leaf.owner=ctx;
    *plan={prepared_leaf.prepared.instructions,end_pc,final_pc,execute,&prepared_leaf};return 1;
} catch (const std::exception& failure) { error(failure.what()); }
catch (...) { error("unknown preparation exception"); }
struct Register {
    Register() {
        const spu_native_leaf descriptor{begin_pc,end_pc,prepare};
        if (spu_native_leaf_register(&descriptor)) error("leaf registration failed");
    }
} registration;
} // namespace
