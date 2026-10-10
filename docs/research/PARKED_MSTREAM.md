# Retail mstream ATRAC hub — PARKED

This is the historical BCES00006 APP_VER03.10 lane, not the current named-US Havok task. Resume only when directed. Addresses below are deterministic for the matched original retail binary; never transplant them into a different revision.

Taskset running/enabled exit semantics, pending-ready signal, TI_ARGS priority and retained LS made the ATRAC hub redispatch/poll for a whole boot. Symptom remained race-load stall/no background video/~11FPS picker; this was not a cure.

flashATRAC staged image 2 LS 33900/entry 90 polls 512B command 49527C80 (ready bit 0): all zeros. Multistream PPU Update tid 3/entry EFE608 is 800us syscall 141 usleep, not event receive. Named-registry passes clear block family CB8A18, repost head to 102CD280, poke 7A120D at 102CD088, PUTLLC flag 102CD000. 158K clears vs one init poison-fill CD8768. CD0378 recycle waits while item stamp [r30+10] equals consumer cursor [[r31]+4]; cursor never diverges.

Five PM image 200 contexts stage jobmod 215 at 4000 without launch; zero observed PCs 4000..16540. Logical/bind scan 11B0/11B8 stops on empty 9C580100. Zero mapped payloads: 49527C80, 4C754600+50, 9C580100, 4950A400, 49322B00/4929B900. 108C0100 next-node unmapped beyond original image end 10310CD0. Corridor 102CD000..102CD0FF saw no SPU PUT/module PUTLLC.

## Exonerated in this lane

Do not reinvestigate without contradictory matched evidence: MFC list engine (EA0 is real base transfer, tag completes), PM claim/stall/ACK cycle, SPU→PPU coherence/shared memory, taskset redispatch, active archive reads, avStream tids 4/5/6 polling with no work. TSTATE 411A/1388 were usleep arguments, not PCs/semaphore waits. Later fixes to shared edge cases do not retroactively convict these specific observations.

## Ranked resume

1. Working RPCS3 same game/revision to menu/race-load; dump 49527C80, 9C580100, 4C754600, descriptor 102CC580, queue 102CD280. Identify first buffer filled and its writer; that names the broken seam.
2. Only if necessary, decode full avStream dequeue trigger entries including StreamCodecMP3 EFF248/Update EFE608 family.
3. Separately verify app-heap mapping if real allocated data above image end is silently zero-filled by VEH; empty pages alone do not prove it.

Historical launch_hub.cmd/logs/hub_pad.txt and memread9/10/find_elf are in temp/legacy/recomp/out/. Old knobs: DMA range 102CC000..102D0000, LS watch 338A0/13100, PPU watch 102CD080 length 80, SPU_SN_DEFER 64, SPU_CTX_LOG 1, FSLOG 1; optional SCTRACE_TID 3. They are archaeological settings, not current defaults. Current [operations](../OPERATIONS.md) owns safe input/guard/capture workflow.
