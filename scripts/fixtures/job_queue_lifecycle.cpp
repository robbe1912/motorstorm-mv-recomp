#include "ppu_recomp.h"
#include "job_queue_lifecycle.h"
#include <cassert>
#include <cstdint>

void motorstorm_observe_queue_reset(ppu_context*);
void motorstorm_observe_queue_init(ppu_context*);
void motorstorm_observe_add_job(ppu_context*);
static job_queue_event events[8];
static unsigned count;
static bool abort_original;
static void event(void*, const job_queue_event& value) noexcept { events[count++] = value; }
void game_original_queue_reset(ppu_context* ctx) { ctx->gpr[3] += 10; if (abort_original) throw 1; }
void game_original_queue_init(ppu_context* ctx) { ctx->gpr[3] += 20; ctx->gpr[4] += 30; }
void game_original_add_job(ppu_context* ctx) { ctx->gpr[5]++; }

int main() {
    ppu_context ctx{}; ctx.gpr[3] = 0x1234; ctx.gpr[4] = 0x5678;
    motorstorm_observe_queue_reset(&ctx);
    assert(ctx.gpr[3] == 0x123e && count == 0);
    job_queue_observer invalid{nullptr, nullptr};
    job_queue_observer owner{nullptr, event};
    assert(!job_queue_observer_install(&invalid));
    assert(job_queue_observer_install(&owner));
    assert(!job_queue_observer_install(&owner));
    motorstorm_observe_queue_init(&ctx);
    assert(count == 2 && ctx.gpr[3] == 0x1252 && ctx.gpr[4] == 0x5696);
    assert(events[0].phase == job_queue_phase::enter && events[1].phase == job_queue_phase::returned);
    assert(events[0].operation == job_queue_operation::init && events[0].call_id && events[0].call_id == events[1].call_id);
    assert(events[0].object == 0x123e && events[0].argument == 0x5678 && events[1].object == 0x123e);
    assert(events[0].context == reinterpret_cast<std::uintptr_t>(&ctx));
    ctx.gpr[5] = 0x123456789abcdef0ULL;
    motorstorm_observe_add_job(&ctx);
    assert(count == 4 && events[2].operation == job_queue_operation::add_job);
    assert(events[2].header == 0x123456789abcdef0ULL && events[3].header == events[2].header);
    assert(events[2].argument == 0x5696 && ctx.gpr[5] == 0x123456789abcdef1ULL);
    abort_original = true;
    try { motorstorm_observe_queue_reset(&ctx); assert(false); } catch (int) {}
    assert(count == 5 && events[4].phase == job_queue_phase::enter && events[4].call_id != events[0].call_id);
    assert(job_queue_observer_install(nullptr));
    abort_original = false;
    motorstorm_observe_queue_reset(&ctx);
    assert(count == 5 && ctx.gpr[3] == 0x1266);
}
