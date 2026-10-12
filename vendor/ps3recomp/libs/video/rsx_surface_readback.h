/* Copy host surface pixels to the big-endian, pitched guest representation. */
#ifndef RSX_SURFACE_READBACK_H
#define RSX_SURFACE_READBACK_H
#include <stdint.h>
#include <stddef.h>
static inline unsigned rsx_surface_readback_bpp(unsigned format) {
    switch(format&31u) { case 4:case 5:case 8:return 4;case 11:return 8;case 12:return 16;default:return 0; }
}
static inline int rsx_surface_readback_rows(void *guest,size_t guest_bytes,unsigned guest_pitch,
    const void *gpu,size_t gpu_bytes,unsigned gpu_pitch,unsigned width,unsigned height,unsigned format) {
    unsigned bpp=rsx_surface_readback_bpp(format);
    if(!guest||!gpu||!width||!height||!bpp||width>UINT32_MAX/bpp)return -1;
    size_t row=(size_t)width*bpp;
    if(guest_pitch<row||gpu_pitch<row||
       (uint64_t)(height-1)*guest_pitch+row>guest_bytes||
       (uint64_t)(height-1)*gpu_pitch+row>gpu_bytes)return -1;
    for(unsigned y=0;y<height;y++) {
        unsigned char *d=(unsigned char *)guest+(size_t)y*guest_pitch;
        const unsigned char *s=(const unsigned char *)gpu+(size_t)y*gpu_pitch;
        if((format&31u)==11)for(size_t i=0;i<row;i+=2){d[i]=s[i+1];d[i+1]=s[i];}
        else if((format&31u)==12)for(size_t i=0;i<row;i+=4){d[i]=s[i+3];d[i+1]=s[i+2];d[i+2]=s[i+1];d[i+3]=s[i];}
        else for(unsigned x=0;x<width;x++){d[x*4]=((format&31u)==8)?s[x*4+3]:255;d[x*4+1]=s[x*4];d[x*4+2]=s[x*4+1];d[x*4+3]=s[x*4+2];}
    }
    return 0;
}
#endif
