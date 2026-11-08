#pragma once

/* Installs an opt-in, fallback-only PPU observer after ppu_recomp_register().
 * It never changes guest state or query results. */
void deformation_depth_observer_install();
