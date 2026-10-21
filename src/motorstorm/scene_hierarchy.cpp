// Game-side ABI bridge; world-transform computation lives in typed host buffers.
#ifdef MOTORSTORM_SCENE_FIXTURE
#include "native_scene_api.h"
#else
#include "ppu_recomp.h"
#endif
#include "world_transforms.h"
#include "native_cpu.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>

void game_original_scene_list_evaluate(ppu_context*);
namespace {
using motorstorm::game::Matrix4;
using motorstorm::game::Float4;
struct State {
    bool enabled=true;
    bool host_supported=motorstorm::game::supports_native_world_transforms();
    std::atomic<unsigned long long> native_calls{0},native_nodes{0},native_ns{0},original_cpu{0},fallbacks{0};
    State() {
        if(const char* mode=std::getenv("MS_NATIVE_HIERARCHY")) {
            if(std::strcmp(mode,"0") && std::strcmp(mode,"1"))
                throw std::invalid_argument("MS_NATIVE_HIERARCHY must be 0 or 1");
            enabled=std::strcmp(mode,"1")==0;
        }
        std::fprintf(stderr,"[native-world] enabled=%u host_avx2_fma=%u\n",unsigned(enabled),unsigned(host_supported));
    }
};
State& state() { static State value; return value; }
void range(std::uint64_t address,std::size_t bytes) {
    if ((bytes && !address) || address>0xffffffffULL || bytes>0x100000000ULL-address)
        throw std::out_of_range("Native hierarchy probe guest range");
}
std::uint32_t swap32(std::uint32_t x) {
    return (x>>24)|((x>>8)&0xff00)|((x<<8)&0xff0000)|(x<<24);
}
template<class T> std::vector<T> read_array(std::uint32_t address,std::size_t count) {
    static_assert(sizeof(T)%4==0);
    range(address,count*sizeof(T));
    std::vector<T> out(count);
    auto* bytes=reinterpret_cast<unsigned char*>(out.data());
    for (std::size_t i=0;i<count*sizeof(T);i+=4) {
        std::uint32_t value;std::memcpy(&value,vm_base+address+i,4);
        value=swap32(value);std::memcpy(bytes+i,&value,4);
    }
    return out;
}
struct Snapshot {
    std::uint32_t object=0,hierarchy=0,count=0;
    std::uint32_t local_ea=0,world_ea=0,parent_ea=0,root_ea=0,translation_ea=0;
    bool dirty=false,topology=false,expected_dirty=false,expected_topology=false;
    std::vector<Matrix4> local,before_world,expected_world;
    std::vector<std::uint32_t> parent,before_root,expected_root;
    std::vector<Float4> before_translation,expected_translation;
};
Snapshot capture(std::uint32_t object) {
    Snapshot s;s.object=object;s.hierarchy=object+12;range(s.hierarchy,36);
    const auto h=s.hierarchy;
    s.count=vm_read32(h+8);
    if (s.count>4096) throw std::out_of_range("Native hierarchy probe node budget");
    s.local_ea=vm_read32(h+12);s.world_ea=vm_read32(h+16);
    s.root_ea=vm_read32(h+20);s.parent_ea=vm_read32(h+24);
    s.dirty=vm_read8(h+28)!=0;s.topology=vm_read8(h+29)!=0;
    s.translation_ea=vm_read32(h+32);
    s.local=read_array<Matrix4>(s.local_ea,s.count);
    s.before_world=read_array<Matrix4>(s.world_ea,s.count);
    s.parent=read_array<std::uint32_t>(s.parent_ea,s.count);
    s.before_root=read_array<std::uint32_t>(s.root_ea,s.count);
    s.before_translation=read_array<Float4>(s.translation_ea,s.count);
    s.expected_world=s.before_world;s.expected_root=s.before_root;
    s.expected_translation=s.before_translation;
    motorstorm::game::WorldTransforms view{s.count,s.local.data(),s.expected_world.data(),s.parent.data(),
        s.expected_root.data(),s.dirty,s.topology};
    motorstorm::game::evaluate_world_transforms(view);
    s.expected_dirty=view.transforms_dirty;s.expected_topology=view.topology_dirty;
    return s;
}
template<class T> std::size_t different_words(const std::vector<T>& a,const std::vector<T>& b) {
    if(a.size()!=b.size()) throw std::logic_error("Native hierarchy output shape");
    std::size_t different=0;
    for(std::size_t i=0;i<a.size()*sizeof(T);i+=4)
        different+=std::memcmp(reinterpret_cast<const char*>(a.data())+i,
                              reinterpret_cast<const char*>(b.data())+i,4)!=0;
    return different;
}
template<class T> void native_commit_array(std::uint32_t address,const std::vector<T>& values) {
    const auto* source=reinterpret_cast<const unsigned char*>(values.data());
    for(std::size_t i=0;i<values.size()*sizeof(T);i+=4) {
        std::uint32_t word;std::memcpy(&word,source+i,4);word=swap32(word);
        std::memcpy(vm_base+address+i,&word,4);
    }
}
struct NativeWork {unsigned dirty=0;unsigned long long nodes=0;};
NativeWork native_scene(std::uint32_t list) {
    range(list,112);
    const auto first=vm_read32(list+20),end=vm_read32(list+92),table=vm_read32(list+96);
    if(first>=end)return {};
    if(end>262144)throw std::out_of_range("Native scene object budget");
    range(table,std::size_t(end)*4);
    struct Guard{std::uint32_t object;unsigned char active,dirty,topology;};
    std::vector<Guard> guards;std::vector<Snapshot> pending;
    NativeWork work;
    for(auto i=first;i<end;++i) {
        const auto object=vm_read32(table+4*i);range(object,64);
        const auto active=vm_read8(object+60),dirty=vm_read8(object+40),topology=vm_read8(object+41);
        guards.push_back({object,active,dirty,topology});
        if(!active)continue;
        if(topology)throw std::runtime_error("Topology-dirty scene requires original reference coverage");
        if(!dirty)continue;
        pending.push_back(capture(object));
        work.nodes+=pending.back().count;++work.dirty;
    }
    struct Span{std::uint64_t first,last;bool write;};
    std::vector<Span> spans;
    auto span=[&](std::uint32_t address,std::size_t size,bool write){range(address,size);if(size)spans.push_back({address,address+std::uint64_t(size),write});};
    span(list,112,false);span(table,std::size_t(end)*4,false);
    for(const auto& g:guards) {
        if(g.active && g.dirty) {
            span(g.object,40,false);span(g.object+42,22,false);span(g.object+40,2,true);
        } else span(g.object,64,false);
    }
    for(const auto& h:pending) {
        span(h.world_ea,h.count*64ull,true);span(h.local_ea,h.count*64ull,false);
        span(h.parent_ea,h.count*4ull,false);span(h.root_ea,h.count*4ull,false);span(h.translation_ea,h.count*16ull,false);
    }
    std::sort(spans.begin(),spans.end(),[](const Span& a,const Span& b){return a.first<b.first;});
    std::uint64_t any_end=0,write_end=0;
    for(const auto& item:spans) {
        if(item.first<(item.write?any_end:write_end))throw std::runtime_error("Native scene buffer overlap");
        any_end=std::max(any_end,item.last);if(item.write)write_end=std::max(write_end,item.last);
    }
    // Complete all host work, then recheck ownership before any guest write.
    if(vm_read32(list+20)!=first||vm_read32(list+92)!=end||vm_read32(list+96)!=table)
        throw std::runtime_error("Native scene list ownership changed");
    for(unsigned i=0;i<guards.size();++i) {
        const auto& g=guards[i];
        if(vm_read32(table+4*(first+i))!=g.object||vm_read8(g.object+60)!=g.active||
           vm_read8(g.object+40)!=g.dirty||vm_read8(g.object+41)!=g.topology)
            throw std::runtime_error("Native scene object ownership changed");
    }
    for(const auto& h:pending) {
        if(vm_read32(h.hierarchy+8)!=h.count||vm_read32(h.hierarchy+12)!=h.local_ea||
           vm_read32(h.hierarchy+16)!=h.world_ea||vm_read32(h.hierarchy+20)!=h.root_ea||
           vm_read32(h.hierarchy+24)!=h.parent_ea||vm_read32(h.hierarchy+32)!=h.translation_ea)
            throw std::runtime_error("Native scene hierarchy ownership changed");
        if(different_words(h.local,read_array<Matrix4>(h.local_ea,h.count))||
           different_words(h.parent,read_array<std::uint32_t>(h.parent_ea,h.count))||
           different_words(h.before_world,read_array<Matrix4>(h.world_ea,h.count))||
           different_words(h.before_root,read_array<std::uint32_t>(h.root_ea,h.count))||
           different_words(h.before_translation,read_array<Float4>(h.translation_ea,h.count)))
            throw std::runtime_error("Native scene data ownership changed");
        if(different_words(h.before_root,h.expected_root))
            throw std::logic_error("Native clean topology changed roots");
    }
    for(const auto& h:pending) {
        native_commit_array(h.world_ea,h.expected_world);
        vm_base[h.hierarchy+28]=0;vm_base[h.hierarchy+29]=0;
    }
    std::atomic_thread_fence(std::memory_order_release);
    return work;
}
}

void motorstorm_scene_evaluate(ppu_context* ctx) {
    State* runtime_state=nullptr;
    try {
        auto& runtime=state();runtime_state=&runtime;
        if(runtime.enabled && runtime.host_supported) {
            if(vm_read8(vm_read32(ctx->gpr[2]+0x4A40))) {
                const auto begin=std::chrono::steady_clock::now();
                const auto work=native_scene(static_cast<std::uint32_t>(ctx->gpr[3]));
                const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-begin).count();
                const auto calls=++runtime.native_calls;
                runtime.native_nodes+=work.nodes;runtime.native_ns+=ns;
                if(calls<=16 || calls%256==0) {
                    std::fprintf(stderr,"[native-world] completed=%llu dirty=%u nodes=%llu total_nodes=%llu total_ns=%llu cpu_original=%llu fallbacks=%llu\n",calls,work.dirty,work.nodes,runtime.native_nodes.load(),runtime.native_ns.load(),runtime.original_cpu.load(),runtime.fallbacks.load());
                    std::fflush(stderr);
                }
                return;
            }
            ++runtime.original_cpu;
        }
    } catch(const std::exception& error) {
        if(runtime_state)++runtime_state->fallbacks;
        std::fprintf(stderr,"[native-world] ORIGINAL fallback list=%08X: %s\n",static_cast<unsigned>(ctx->gpr[3]),error.what());
        std::fflush(stderr);
    }
    // All fallible preparation precedes commits; the retained original owns
    // unsupported work, including its jobs and completion synchronization.
    game_original_scene_list_evaluate(ctx);
}
