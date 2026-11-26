/* Interpreter include of the replay engine, for particle_bind_harness.c.
   The build passes this file as MOTORSTORM_REPLAY_INTERP to the engine
   (scripts/fixtures/particle_random_replay.c). The harness supplies the program entry, so
   the main function of the engine itself gets another name. */
#include "../../vendor/ps3recomp/runtime/spu/spu_interp.c"
#define main particle_bind_engine_main
