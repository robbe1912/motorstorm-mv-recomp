#include "native_scene_api.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>
#include <immintrin.h>
#include "native_cpu.h"
static std::vector<std::uint8_t> bytes(1024*1024),before;
std::uint8_t* vm_base=bytes.data();
static unsigned calls=0,csr_before=0;
void motorstorm_scene_evaluate(ppu_context*);
void check(bool ok,const char* label){if(!ok)throw std::runtime_error(label);}
void bounds(std::uint64_t a,std::size_t n){check(a<=bytes.size()&&n<=bytes.size()-a,"Fixture bounds");}
std::uint8_t vm_read8(std::uint64_t a){bounds(a,1);return bytes[a];}
std::uint32_t vm_read32(std::uint64_t a){bounds(a,4);return(std::uint32_t(bytes[a])<<24)|(std::uint32_t(bytes[a+1])<<16)|(std::uint32_t(bytes[a+2])<<8)|bytes[a+3];}
void word(unsigned a,std::uint32_t v){bounds(a,4);for(unsigned i=0;i<4;++i)bytes[a+i]=std::uint8_t(v>>(24-8*i));}
void scalar(unsigned a,float f){std::uint32_t v;std::memcpy(&v,&f,4);word(a,v);}
void matrix(unsigned a,float x,float y,float z){for(unsigned r=0;r<4;++r)for(unsigned c=0;c<4;++c)scalar(a+16*r+4*c,r==c?1.f:0.f);scalar(a+48,x);scalar(a+52,y);scalar(a+56,z);}
void prepare(ppu_context& ctx){
 std::fill(bytes.begin(),bytes.end(),0);ctx={};ctx.gpr[2]=0x20000;ctx.gpr[3]=0x1000;
 word(0x24a40,0x30000);bytes[0x30000]=1;
 word(0x1014,0);word(0x105c,1);word(0x1060,0x1800);word(0x1800,0x2000);bytes[0x203c]=1;
 const unsigned h=0x200c;word(h+8,2);word(h+12,0x4000);word(h+16,0x5000);word(h+20,0x6000);word(h+24,0x7000);word(h+32,0x8000);bytes[h+28]=1;
 word(0x6000,0);word(0x6004,0);word(0x7000,0);word(0x7004,0);
 matrix(0x4000,3,5,7);matrix(0x4040,11,13,17);matrix(0x5000,99,98,97);matrix(0x5040,96,95,94);
 calls=0;
}
void game_original_scene_list_evaluate(ppu_context*){
 check(bytes==before,"No partial native commit before original fallback");
 check(_mm_getcsr()==csr_before,"FP state at original fallback");++calls;
}
void invoke(ppu_context& ctx){before=bytes;csr_before=_mm_getcsr();auto prior=ctx;motorstorm_scene_evaluate(&ctx);check(_mm_getcsr()==csr_before,"Adapter FP restoration");check(!std::memcmp(&prior,&ctx,sizeof ctx),"Context preservation");}
int main(int argc,char**){try{

 constexpr unsigned required=(1u<<12)|(1u<<26)|(1u<<27)|(1u<<28);
 check(motorstorm::game::world_transform_features(7,required,32,6),"Complete native CPU features");
 for(unsigned bit:{12u,26u,27u,28u})check(!motorstorm::game::world_transform_features(7,required^(1u<<bit),32,6),"Missing CPU feature rejected");
 for(unsigned state:{0u,2u,4u})check(!motorstorm::game::world_transform_features(7,required,32,state),"Missing OS vector state rejected");
 check(!motorstorm::game::world_transform_features(6,required,32,6),"Missing CPUID leaf rejected");
 check(!motorstorm::game::world_transform_features(7,required,0,6),"Missing AVX2 rejected");
 check(motorstorm::game::supports_native_world_transforms(),"Host supports native fixture");
 ppu_context ctx;prepare(ctx);auto saved=bytes;
 if(argc>1){invoke(ctx);check(calls==1&&bytes==saved,"Disabled native path retains original");std::puts("PASS original reference mode");return 0;}
 matrix(0x5000,3,5,7);matrix(0x5040,14,18,24);bytes[0x2028]=0;auto expected=bytes;bytes=saved;vm_base=bytes.data();
 invoke(ctx);check(calls==0&&bytes==expected,"Native world/flag transaction");
 prepare(ctx);bytes[0x2028]=0;word(0x2014,200000);word(0x2018,0);word(0x201c,0);saved=bytes;
 invoke(ctx);check(!calls&&bytes==saved,"Clean hierarchy does no matrix work");
 prepare(ctx);bytes[0x203c]=0;saved=bytes;invoke(ctx);check(!calls&&bytes==saved,"Inactive object preserved");
 prepare(ctx);word(0x1014,2);word(0x105c,1);word(0x1060,0);saved=bytes;invoke(ctx);check(!calls&&bytes==saved,"Empty range requires no object array");
 prepare(ctx);word(0x105c,2);word(0x1804,0x2400);bytes[0x243c]=1;bytes[0x2428]=1;bytes[0x2429]=1;saved=bytes;
 invoke(ctx);check(calls==1&&bytes==saved,"Whole-list topology fallback without writes");
 prepare(ctx);bytes[0x2028]=0;bytes[0x2029]=1;saved=bytes;invoke(ctx);
 check(calls==1&&bytes==saved,"Topology-only dirty work must retain original execution");
 prepare(ctx);word(0x202c,0x5000);saved=bytes;invoke(ctx);check(calls==1&&bytes==saved,"Overlapping scratch fallback without writes");
 prepare(ctx);word(0x105c,2);word(0x1804,0x2400);word(0x201c,0x2400);saved=bytes;
 invoke(ctx);check(calls==1&&bytes==saved,"Inactive object metadata cannot overlap world writes");
 prepare(ctx);word(0x4000,0x7f800000);saved=bytes;invoke(ctx);check(calls==1&&bytes==saved,"Numeric range fallback without writes");
 prepare(ctx);bytes[0x30000]=0;saved=bytes;invoke(ctx);check(calls==1&&bytes==saved,"Original CPU mode preserved");
 std::puts("PASS native adapter: real world/flag commit, no original on supported work, whole-list fallbacks without writes, clean/inactive/empty cases, context/FP preservation");return 0;
}catch(const std::exception& e){std::fprintf(stderr,"FAIL: %s\n",e.what());return 1;}}
