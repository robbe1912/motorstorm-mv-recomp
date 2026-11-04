/* Recording and executing command lists borrow objects, not COM references.
 * Keep distinct used objects alive until a checked GPU retirement succeeds. */
#ifndef RSX_GPU_REFERENCES_H
#define RSX_GPU_REFERENCES_H
#ifndef RSX_GPU_REFERENCES_MAX
#define RSX_GPU_REFERENCES_MAX 2048
#endif
typedef struct rsx_gpu_references {
 void *objects[RSX_GPU_REFERENCES_MAX];unsigned count;
} rsx_gpu_references;
typedef struct rsx_gpu_reference_ops {
 void *context;
 void (*retain)(void *context,void *object);
 void (*release)(void *context,void *object);
 int (*retire)(void *context);
} rsx_gpu_reference_ops;
static int rsx_gpu_reference_hold(rsx_gpu_references *refs,void *object,const rsx_gpu_reference_ops *ops) {
 if(!object)return 0;
 for(unsigned i=0;i<refs->count;++i)if(refs->objects[i]==object)return 1;
 if(refs->count>=RSX_GPU_REFERENCES_MAX)return 0;
 ops->retain(ops->context,object);refs->objects[refs->count++]=object;return 1;
}
static int rsx_gpu_reference_retire(rsx_gpu_references *refs,const rsx_gpu_reference_ops *ops) {
 if(!ops->retire(ops->context))return 0;
 for(unsigned i=0;i<refs->count;++i){ops->release(ops->context,refs->objects[i]);refs->objects[i]=0;}
 refs->count=0;return 1;
}
#endif
