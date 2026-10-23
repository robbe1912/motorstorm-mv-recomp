/* Authored bytecode only; no title payload or graphics device. */
#include "rsx_fp_decompiler.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif
static unsigned hash_calls;
#ifdef FP_SNAPSHOT_VERIFY_COUNTS
static u64 counted_hash(const u8*p,u32 n,u64 seed){hash_calls++;return rsx_fp_structural_hash(p,n,seed);}
#define rsx_fp_structural_hash counted_hash
#endif
#include "rsx_fp_snapshot.h"
#ifdef FP_SNAPSHOT_VERIFY_COUNTS
#undef rsx_fp_structural_hash
#endif
static u8 bound[4096],live[4096];
static volatile unsigned sink;
#define CHECK(c,m) do{if(!(c)){fprintf(stderr,"FAIL %s\n",m);exit(1);}}while(0)
static void word(u8*p,u32 w){w=(w<<16)|(w>>16);p[0]=(u8)(w>>24);p[1]=(u8)(w>>16);p[2]=(u8)(w>>8);p[3]=(u8)w;}
static u32 program(unsigned instructions,int constant){
    memset(bound,0,sizeof bound);u32 off=0;
    for(unsigned i=0;i<instructions;i++){
        word(bound+off,0x01001E00u|(i+1==instructions));
        word(bound+off+4,(constant?2u:1u)|0x1C9DC000u);
        word(bound+off+8,0);word(bound+off+12,0);off+=16;
        if(constant){for(int j=0;j<16;j++)bound[off+j]=(u8)(i*7+j);off+=16;}
    }
    return off;
}
#ifdef _MSC_VER
#define NOINLINE __declspec(noinline)
#else
#define NOINLINE __attribute__((noinline))
#endif
static NOINLINE int original(const u8*l,const u8*b,u32 size,u32 cap,u64 hash){
    u64 h=rsx_fp_structural_hash(l,cap,0);
    return h==hash && memcmp(l,b,size)!=0 ? RSX_FP_SNAPSHOT_REFRESH:RSX_FP_SNAPSHOT_KEEP;
}
static NOINLINE int candidate(const u8*l,const u8*b,u32 size,u32 cap,u64 hash){return rsx_fp_snapshot_check(l,b,size,cap,hash);}
static void parity(u32 size,u64 hash,int expected,const char*message){
    CHECK(original(live,bound,size,4096,hash)==expected,"original authored decision");
    CHECK(candidate(live,bound,size,4096,hash)==expected,message);
}
static double now(void){
#ifdef _WIN32
    LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);return(double)t.QuadPart/f.QuadPart;
#else
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;
#endif
}
static double cpu_now(void){
#ifdef _WIN32
    FILETIME c,e,k,u;CHECK(GetProcessTimes(GetCurrentProcess(),&c,&e,&k,&u),"self process CPU timer");
    ULARGE_INTEGER a,b;a.LowPart=k.dwLowDateTime;a.HighPart=k.dwHighDateTime;b.LowPart=u.dwLowDateTime;b.HighPart=u.dwHighDateTime;return(double)(a.QuadPart+b.QuadPart)*1e-7;
#else
    struct timespec t;CHECK(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t)==0,"self process CPU timer");return t.tv_sec+t.tv_nsec*1e-9;
#endif
}
int main(int argc,char**argv){
    if(argc==5){
        unsigned n=(unsigned)strtoul(argv[2],NULL,10),iterations=(unsigned)strtoul(argv[3],NULL,10);int edit=atoi(argv[4]);
        CHECK(n && n<=128 && iterations && (edit==0||edit==1),"benchmark parameters");
        u32 size=program(n,1);u64 hash=rsx_fp_structural_hash(bound,4096,0);CHECK(hash && rsx_fp_program_size(bound,4096)==size,"valid benchmark bytecode");
        memcpy(live,bound,sizeof live);if(edit)live[16]^=1;
        int (*volatile fn)(const u8*,const u8*,u32,u32,u64)=strcmp(argv[1],"original")==0?original:candidate;
        CHECK(strcmp(argv[1],"original")==0||strcmp(argv[1],"candidate")==0,"benchmark side");
        for(unsigned i=0;i<1000;i++)sink+=(unsigned)fn(live,bound,size,4096,hash);sink=0;
        double cpu_start=cpu_now();double start=now();for(unsigned i=0;i<iterations;i++)sink+=(unsigned)fn(live,bound,size,4096,hash);double elapsed=now()-start;double cpu=cpu_now()-cpu_start;
        CHECK(sink==iterations*(unsigned)edit,"benchmark output work checksum");
        printf("{\"side\":\"%s\",\"bytes\":%u,\"edit\":%d,\"iterations\":%u,\"checksum\":%u,\"seconds\":%.9f,\"cpu_seconds\":%.9f}\n",argv[1],size,edit,iterations,sink,elapsed,cpu);return 0;
    }
    const unsigned sizes[]={1,2,7,32,64,128};
    for(unsigned c=0;c<2;c++)for(unsigned j=0;j<6;j++){
        u32 size=program(sizes[j],(int)c);u64 hash=rsx_fp_structural_hash(bound,4096,0);CHECK(hash && rsx_fp_program_size(bound,4096)==size,"authored program extent/hash");
        memcpy(live,bound,sizeof live);hash_calls=0;CHECK(candidate(live,bound,size,4096,hash)==0,"identical snapshot decision");
#ifdef FP_SNAPSHOT_VERIFY_COUNTS
        CHECK(hash_calls==0,"unchanged snapshot redundantly rehashed");
#endif
        parity(size,hash,0,"identical snapshot parity");
        if(c){memcpy(live,bound,sizeof live);live[16]^=1;parity(size,hash,1,"inline constant refresh");}
        memcpy(live,bound,sizeof live);live[2]^=3;parity(size,hash,0,"recycled structural program stays bound");
        for(u32 k=0;k<size;k++){
            memcpy(live,bound,sizeof live);live[k]^=(u8)(1u<<(k%8));
            int expected=original(live,bound,size,4096,hash);
            CHECK(candidate(live,bound,size,4096,hash)==expected,"mutated program/constant decision");
        }
        memset(live,0,sizeof live);parity(size,hash,0,"malformed live code stays bound");
        memcpy(live,bound,sizeof live);if(size<4096)live[size]^=0x55;parity(size,hash,0,"bytes after actual program ignored");
    }
    CHECK(candidate(NULL,bound,16,4096,1)==-1 && candidate(live,NULL,16,4096,1)==-1 && candidate(live,bound,0,4096,1)==-1 && candidate(live,bound,4097,4096,1)==-1 && candidate(live,bound,16,4096,0)==-1,"invalid snapshot metadata admission");
    puts("PASS actual FP snapshot helper and original decisions; mutations/constants/recycled/malformed/extent cases");return 0;
}
