/* Bounded compile-only worker pool. Renderer caches and device objects are
 * never accessed by workers. Keys are deep-copied and compared byte-for-byte.
 * The owner retains pool/user storage until shutdown succeeds. Callbacks may
 * not reenter the pool. Job sources remain owned until worker completion. */
#ifndef RSX_FXC_POOL_H
#define RSX_FXC_POOL_H
#ifdef _WIN32
#include <windows.h>
#include "rsx_shader_cache.h"
#ifndef RSX_FXC_POOL_JOBS
#define RSX_FXC_POOL_JOBS 192
#endif
#define RSX_FXC_POOL_INPUT_BYTES (16u*1024u*1024u)
#define RSX_FXC_POOL_OUTPUT_BYTES (32u*1024u*1024u)
typedef int (*rsx_fxc_compile)(void*,const rsx_shader_key*,void**,size_t*);
typedef void (*rsx_fxc_release)(void*,void*);
typedef struct {
    rsx_shader_key key;void* storage;void* blob;size_t bytes;
    uint64_t generation;unsigned state,success,claiming;
} rsx_fxc_job;
typedef struct {
    CRITICAL_SECTION lock;CONDITION_VARIABLE work,done;
    HANDLE threads[16];unsigned count,stopping,failed,claimers;
    size_t input_bytes,output_bytes;
    rsx_fxc_compile compile;rsx_fxc_release release;void* user;
    rsx_fxc_job jobs[RSX_FXC_POOL_JOBS];
} rsx_fxc_pool;
static unsigned rsx_fxc_default_threads(unsigned processors)
{ return processors>1 ? (processors-1<8?processors-1:8):0; }
static void rsx_fxc_job_free(rsx_fxc_pool* p,rsx_fxc_job* j)
{
    if(j->blob){p->release(p->user,j->blob);p->output_bytes-=j->bytes;}
    if(j->storage){p->input_bytes-=j->key.bytes;free(j->storage);}
    memset(j,0,sizeof(*j));
}
static rsx_fxc_job* rsx_fxc_find(rsx_fxc_pool* p,const rsx_shader_key* k)
{
    for(unsigned i=0;i<RSX_FXC_POOL_JOBS;i++)
        if(p->jobs[i].state && rsx_shader_key_equal(&p->jobs[i].key,k))return &p->jobs[i];
    return NULL;
}
static void rsx_fxc_fail_queued(rsx_fxc_pool* p)
{
    p->failed=1;
    for(unsigned i=0;i<RSX_FXC_POOL_JOBS;i++)
        if(p->jobs[i].state==1){p->jobs[i].state=3;p->jobs[i].success=0;}
    WakeAllConditionVariable(&p->done);WakeAllConditionVariable(&p->work);
}
static DWORD WINAPI rsx_fxc_worker(LPVOID context)
{
    rsx_fxc_pool* p=(rsx_fxc_pool*)context;
    for(;;){
        EnterCriticalSection(&p->lock);rsx_fxc_job* j=NULL;
        for(;;){
            if(p->stopping || p->failed){LeaveCriticalSection(&p->lock);return 0;}
            for(unsigned i=0;i<RSX_FXC_POOL_JOBS;i++)if(p->jobs[i].state==1){j=&p->jobs[i];break;}
            if(j)break;
            if(!SleepConditionVariableCS(&p->work,&p->lock,INFINITE)){
                rsx_fxc_fail_queued(p);LeaveCriticalSection(&p->lock);return 0;
            }
        }
        j->state=2;LeaveCriticalSection(&p->lock);
        void* blob=NULL;size_t bytes=0;int success=p->compile(p->user,&j->key,&blob,&bytes);
        EnterCriticalSection(&p->lock);
        if(!success || !blob || !bytes || bytes>RSX_FXC_POOL_OUTPUT_BYTES-p->output_bytes){
            if(blob)p->release(p->user,blob);blob=NULL;bytes=0;success=0;
        }
        j->blob=blob;j->bytes=bytes;j->success=success!=0;p->output_bytes+=bytes;j->state=3;
        WakeAllConditionVariable(&p->done);LeaveCriticalSection(&p->lock);
    }
}
static rsx_fxc_pool* rsx_fxc_pool_create(unsigned threads,rsx_fxc_compile compile,
                                       rsx_fxc_release release,void* user)
{
    if(!threads || threads>16 || !compile || !release)return NULL;
    rsx_fxc_pool* p=(rsx_fxc_pool*)calloc(1,sizeof(*p));if(!p)return NULL;
    InitializeCriticalSection(&p->lock);InitializeConditionVariable(&p->work);InitializeConditionVariable(&p->done);
    p->compile=compile;p->release=release;p->user=user;
    for(unsigned i=0;i<threads;i++){
        HANDLE thread=CreateThread(NULL,0,rsx_fxc_worker,p,0,NULL);
        if(thread)p->threads[p->count++]=thread;
    }
    if(!p->count){DeleteCriticalSection(&p->lock);free(p);return NULL;}
    return p;
}
static int rsx_fxc_pool_enqueue(rsx_fxc_pool* p,const rsx_shader_key* k,uint64_t generation)
{
    if(!p || !k || !k->source || !k->bytes || !k->name || !k->entry || !k->target)return 0;
    int accepted=0;EnterCriticalSection(&p->lock);
    if(p->stopping || p->failed)goto done;
    rsx_fxc_job* same=rsx_fxc_find(p,k);
    if(same){same->generation=generation;accepted=1;goto done;}
    rsx_fxc_job* slot=NULL;
    for(unsigned i=0;i<RSX_FXC_POOL_JOBS;i++){
        rsx_fxc_job* j=&p->jobs[i];
        if(j->state==3 && !j->claiming && generation>=j->generation && generation-j->generation>=2)
            rsx_fxc_job_free(p,j);
        if(!j->state && !slot)slot=j;
    }
    if(slot && k->bytes<=RSX_FXC_POOL_INPUT_BYTES-p->input_bytes){
        rsx_shader_key saved;void* storage=NULL;
        if(rsx_shader_key_copy(k,&saved,&storage)){
            slot->key=saved;slot->storage=storage;slot->generation=generation;slot->state=1;
            p->input_bytes+=k->bytes;accepted=1;WakeConditionVariable(&p->work);
        }
    }
done:
    LeaveCriticalSection(&p->lock);return accepted;
}
/* One claimant leases a job while the CS is released. A second claimant
 * falls back synchronously rather than freeing a source under the worker. */
static int rsx_fxc_pool_claim(rsx_fxc_pool* p,const rsx_shader_key* k,void** blob)
{
    if(!p || !blob || !k || !k->source || !k->bytes || !k->name || !k->entry || !k->target)return 0;
    *blob=NULL;
    int success=0,leased=0;EnterCriticalSection(&p->lock);
    rsx_fxc_job* j=rsx_fxc_find(p,k);
    if(!j || j->claiming)goto done;
    j->claiming=1;leased=1;p->claimers++;
    while(j->state!=3){
        if(!SleepConditionVariableCS(&p->done,&p->lock,15000)){
            j->claiming=0;goto done; /* Running source remains owned. */
        }
    }
    if(j->success && j->blob){
        *blob=j->blob;p->output_bytes-=j->bytes;j->blob=NULL;success=1;
    }
    rsx_fxc_job_free(p,j);
done:
    if(leased){p->claimers--;WakeAllConditionVariable(&p->done);}
    LeaveCriticalSection(&p->lock);return success;
}
/* A timeout leaves storage/locks alive for a still-running callback.
 * Stop admitting new API callers before shutdown. Existing claimers drain.
 * Call again after it finishes, or retain the allocation until process exit. */
static int rsx_fxc_pool_shutdown(rsx_fxc_pool* p,DWORD timeout)
{
    if(!p)return 1;
    EnterCriticalSection(&p->lock);p->stopping=1;rsx_fxc_fail_queued(p);LeaveCriticalSection(&p->lock);
    if(WaitForMultipleObjects(p->count,p->threads,TRUE,timeout)!=WAIT_OBJECT_0)return 0;
    EnterCriticalSection(&p->lock);
    ULONGLONG began=GetTickCount64();
    while(p->claimers){
        ULONGLONG elapsed=GetTickCount64()-began;
        if(elapsed>=timeout || !SleepConditionVariableCS(&p->done,&p->lock,(DWORD)(timeout-elapsed))){
            LeaveCriticalSection(&p->lock);return 0;
        }
    }
    LeaveCriticalSection(&p->lock);
    for(unsigned i=0;i<p->count;i++)CloseHandle(p->threads[i]);
    for(unsigned i=0;i<RSX_FXC_POOL_JOBS;i++)rsx_fxc_job_free(p,&p->jobs[i]);
    DeleteCriticalSection(&p->lock);free(p);return 1;
}
#endif
#endif
