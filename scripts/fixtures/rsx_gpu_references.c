/* Authored cache churn reproduces early destruction of a recorded PSO. */
#define RSX_GPU_REFERENCES_MAX 512
#include "rsx_gpu_references.h"
#include <stdio.h>
#include <string.h>
typedef struct object {unsigned refs,retains,releases;} object;
static unsigned checks,failures,retire_calls;static int completed;
static void retain(void *c,void *p){(void)c;object *o=p;++o->refs;++o->retains;}
static void release(void *c,void *p){(void)c;object *o=p;if(!o->refs){fprintf(stderr,"double release\n");failures++;return;}--o->refs;++o->releases;}
static int retire(void *c){(void)c;++retire_calls;return completed;}
static void check(int ok,const char *n){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",n);++failures;}}
int main(int argc,char **argv){
 int legacy=argc>1 && !strcmp(argv[1],"--no-recorded-reference");rsx_gpu_references held={0};
 rsx_gpu_reference_ops ops={0,retain,release,retire};object objects[513]={0};
 for(unsigned i=0;i<276;++i){objects[i].refs=1;if(!legacy && !rsx_gpu_reference_hold(&held,&objects[i],&ops))return 2;if(i>=256)release(0,&objects[i-256]);}
 check(objects[0].refs>0,"recorded PSO survives 256-entry cache eviction");
 check(held.count==(legacy?0u:276u),"distinct references");
 for(unsigned i=20;i<276;++i)release(0,&objects[i]);
 check(!rsx_gpu_reference_retire(&held,&ops),"failed retirement is reported");
 check(held.count==(legacy?0u:276u) && (legacy || objects[0].refs==1),"failed retirement preserves ownership");
 completed=1;check(rsx_gpu_reference_retire(&held,&ops) && !held.count,"completed retirement releases ownership");
 unsigned live=0;for(unsigned i=0;i<276;++i)live+=objects[i].refs;
 check(!live,"no references remain after completion");
 object repeated={1,0,0};check(rsx_gpu_reference_hold(&held,&repeated,&ops) && rsx_gpu_reference_hold(&held,&repeated,&ops) && repeated.retains==1 && held.count==1,"deduplicate repeated binding");
 release(0,&repeated);check(rsx_gpu_reference_retire(&held,&ops) && !repeated.refs,"deduplicated ownership released once");
 memset(objects,0,sizeof(objects));
 for(unsigned i=0;i<513;++i)objects[i].refs=1;
 for(unsigned i=0;i<512;++i)if(!rsx_gpu_reference_hold(&held,&objects[i],&ops))return 2;
 check(!rsx_gpu_reference_hold(&held,&objects[512],&ops) && objects[512].refs==1,"capacity refuses without changing ownership");
 for(unsigned i=0;i<513;++i)release(0,&objects[i]);
 check(rsx_gpu_reference_retire(&held,&ops) && !held.count,"bounded collection retires");
 completed=0;unsigned calls=retire_calls;check(!rsx_gpu_reference_retire(&held,&ops) && retire_calls==calls+1,"empty collection still checks shared GPU retirement");
 printf("checks=%u failures=%u\n",checks,failures);return failures?1:0;
}
