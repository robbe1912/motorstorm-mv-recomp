#include "rsx_record_batch.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
typedef struct command { unsigned sequence, clear, value; } command;
typedef struct fixture {
    rsx_record_batch batch;
    command commands[4]; uint32_t count;
    unsigned executed, implicit_clears, explicit_clears, presents, pixel, submits;
} fixture;
static void submit(void* context, int present)
{
    fixture* f = context; ++f->submits;
    if (rsx_record_batch_begin(&f->batch)) { f->pixel = 0; ++f->implicit_clears; }
    for (unsigned i = 0; i < f->count; ++i) {
        command* c = &f->commands[i]; CHECK(c->sequence == f->executed++);
        if (c->clear) { f->pixel = c->value; ++f->explicit_clears; }
        else { f->pixel += c->value; rsx_record_batch_display_write(&f->batch); }
    }
    memset(f->commands, 0xDA, sizeof(f->commands)); f->count = 0;
    if (present) { ++f->presents; rsx_record_batch_presented(&f->batch); }
}
int main(void)
{
    fixture f = {0}; unsigned expected = 0, clears = 0;
    for (unsigned n = 0; n < 15; ++n) {
        CHECK(rsx_record_batch_room(&f.count, 4, &f, submit));
        command c = {n, n == 0 || n == 6, n + 1};
        f.commands[f.count++] = c;
        if (c.clear) { expected = c.value; ++clears; } else expected += c.value;
        CHECK(f.presents == 0);
    }
    CHECK(f.submits == 3 && f.executed == 12 && f.batch.display_written);
    submit(&f, 0); /* Remaining work can be offscreen at the guest flip. */
    CHECK(f.executed == 15 && f.pixel == expected && f.explicit_clears == clears);
    CHECK(f.implicit_clears == 1 && f.presents == 0 && f.batch.display_written);
    submit(&f, f.batch.display_written);
    CHECK(f.presents == 1 && f.pixel == expected && !f.batch.display_written);
    CHECK(!f.batch.backing_initialized);
    CHECK(rsx_record_batch_begin(&f.batch)); /* Next presented image starts fresh. */
    CHECK(!rsx_record_batch_begin(&f.batch));
    f.count = 5; unsigned before = f.submits;
    CHECK(!rsx_record_batch_room(&f.count, 4, &f, submit));
    CHECK(!rsx_record_batch_room(&f.count, 0, &f, submit));
    CHECK(f.submits == before); /* Corruption is not passed to a bounded array. */
    puts("PASS: ordered capacity drains preserve clears/data and defer presentation to flip");
    return 0;
}
