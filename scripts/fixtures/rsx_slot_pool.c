#include "rsx_slot_pool.h"
#include <stdio.h>
static unsigned checks,failures;
static void check(int ok,const char* label){checks++;if(!ok){failures++;printf("FAIL %s\n",label);}}
int main(int argc,char** argv){
 int legacy=argc==2&&!strcmp(argv[1],"--fixed96"),complete=1,zero=1;unsigned cap=0;size_t* slots=NULL;
 for(unsigned i=0;i<100;i++){
  if(i==cap){unsigned next=cap;void* p=rsx_slot_pool_grow(slots,cap,i+1,96,legacy?96:320,sizeof(*slots),&next);if(!p){complete=0;break;}slots=p;for(unsigned j=cap;j<next;j++)if(slots[j])zero=0;cap=next;}
  slots[i]=i+1;
 }
 check(complete,"all100 requested textures admitted");int intact=1;for(unsigned i=0;i<96;i++)if(slots[i]!=i+1)intact=0;
 check(intact,"earlier recorded resource identities preserved");check(zero,"new metadata zeroed");check(cap<=320,"working-set bound");
 unsigned next=cap;check(!rsx_slot_pool_grow(slots,cap,321,96,320,sizeof(*slots),&next)&&next==cap&&slots[0]==1,"bound failure preserves owners");
 check(!rsx_slot_pool_grow(slots,cap,cap+1,96,320,SIZE_MAX,&next),"byte overflow rejected");
 check(rsx_slot_pool_grow(slots,cap,cap,96,320,sizeof(*slots),&next)==slots&&next==cap,"no-growth identity");
 check(!rsx_slot_pool_grow(slots,cap,cap+1,96,320,0,&next),"zero stride rejected");
 check(!rsx_slot_pool_grow(NULL,1,2,96,320,sizeof(*slots),&next),"invalid owner rejected");free(slots);
 printf("checks=%u failures=%u\n",checks,failures);return failures?1:0;
}
