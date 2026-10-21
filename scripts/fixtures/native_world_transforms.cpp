#include "world_transforms.h"
#include <immintrin.h>
#include <cstdio>
#include <cstring>
#include <stdexcept>
using namespace motorstorm::game;
std::uint32_t bits(float f){std::uint32_t x;std::memcpy(&x,&f,4);return x;}
Matrix4 identity(){return Matrix4{{{{1,0,0,0}},{{0,1,0,0}},{{0,0,1,0}},{{0,0,0,1}}}};}
void check(bool ok,const char* label){if(!ok)throw std::runtime_error(label);}
int main(){try{
 const auto caller=_mm_getcsr();
 for(unsigned round:{0u,0x2000u,0x4000u,0x6000u}){
  _mm_setcsr((caller&~0x6000u)|round|0x20u);const auto saved=_mm_getcsr();
  Matrix4 local[2]={identity(),identity()},world[2]{};std::uint32_t parent[2]={0,0},root[2]={99,99};
  local[0].row[0].value[0]=1.5f;local[1].row[0].value[0]=1.00000011920928955078125f;
  WorldTransforms h{2,local,world,parent,root,true,true};evaluate_world_transforms(h);
  check(bits(world[1].row[0].value[0])==0x3fc00001u,"Independent toward-zero product oracle");
  check(_mm_getcsr()==saved,"FP environment restoration");check(root[0]==0&&root[1]==0&&!h.transforms_dirty&&!h.topology_dirty,"Root topology and dirty flags");
  local[0]=identity();local[1]=identity();local[0].row[2].value[0]=0.99999988079071044921875f;local[1].row[0]=Float4{{-1,0,1.00000011920928955078125f,0}};
  h.transforms_dirty=true;evaluate_world_transforms(h);check(bits(world[1].row[0].value[0])==0xa8800000u,"Independent fused cancellation oracle");check(_mm_getcsr()==saved,"Fused FP restoration");
  local[0]=Matrix4{{{{0,1,0,0}},{{-1,0,0,0}},{{0,0,1,0}},{{3,5,7,1}}}};local[1]=identity();local[1].row[3]=Float4{{11,13,17,1}};
  h.transforms_dirty=true;evaluate_world_transforms(h);
  check(world[1].row[3].value[0]==-10&&world[1].row[3].value[1]==16&&world[1].row[3].value[2]==24&&world[1].row[3].value[3]==1,"Independent rotation/translation oracle");
  check(_mm_getcsr()==saved,"Analytic FP restoration");
  h.transforms_dirty=true;parent[0]=1;bool rejected=false;
  try{evaluate_world_transforms(h);}catch(const std::invalid_argument&){rejected=true;}
  check(rejected&&_mm_getcsr()==saved,"Forward parent rejection and FP preservation");
  parent[0]=0;root[1]=1;rejected=false;
  try{evaluate_world_transforms(h);}catch(const std::invalid_argument&){rejected=true;}
  check(rejected&&_mm_getcsr()==saved,"Wrong root rejection and FP preservation");
  root[1]=0;const std::uint32_t infinity=0x7f800000u;std::memcpy(&local[0].row[0].value[0],&infinity,4);rejected=false;
  try{evaluate_world_transforms(h);}catch(const std::domain_error&){rejected=true;}
  check(rejected&&_mm_getcsr()==saved,"Non-finite input rejection and FP restoration");
  WorldTransforms empty{0,nullptr,nullptr,nullptr,nullptr,true,true};evaluate_world_transforms(empty);
  check(!empty.transforms_dirty&&!empty.topology_dirty&&_mm_getcsr()==saved,"Empty hierarchy and FP restoration");
 }
 _mm_setcsr(caller);std::puts("PASS: 4 caller FP modes, rational rounding/fusion oracles, rotation/translation, roots, flags and FP restoration");return 0;
}catch(const std::exception&e){std::fprintf(stderr,"FAIL: %s\n",e.what());return 1;}}
