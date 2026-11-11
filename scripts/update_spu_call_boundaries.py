#!/usr/bin/env python3
"""Update known generated call brackets into a separate, provenance-recorded copy."""
import argparse,hashlib,json,re
from pathlib import Path
IMAGE=r'int32_t _si = \(int32_t\)ctx->image_id; '
RESTORE=r' spu_img_restore\(ctx, _si\);'
OLD=re.compile(IMAGE+r'(?P<body>[^{}\n]*spu_drain_call\(ctx, (?P<ret>0x[0-9A-Fa-f]+)\); ctx->host_depth--;)' + RESTORE)
NEW=re.compile(IMAGE+r'uint32_t _sr = ctx->drain_ret_pc; ctx->drain_ret_pc = (?P<ret>0x[0-9A-Fa-f]+); (?P<body>[^{}\n]*spu_drain_call\(ctx, (?P=ret)\); ctx->host_depth--;)' + r' ctx->drain_ret_pc = _sr;' + RESTORE)
def update(source):
    old=list(OLD.finditer(source));new=list(NEW.finditer(source))
    total=source.count('spu_drain_call(ctx,')
    if len(old)+len(new)!=total:raise ValueError('unrecognized generated call bracket: refusing partial update')
    def replace(m):
        return ('int32_t _si = (int32_t)ctx->image_id; uint32_t _sr = ctx->drain_ret_pc; '
                'ctx->drain_ret_pc = '+m['ret']+'; '+m['body']+
                ' ctx->drain_ret_pc = _sr; spu_img_restore(ctx, _si);')
    return OLD.sub(replace,source),len(old),len(new)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path);ap.add_argument('output',type=Path);args=ap.parse_args()
    if args.source.resolve()==args.output.resolve():ap.error('output must be a separate copy')
    if args.output.exists():ap.error('output must not already exist')
    original=args.source.read_bytes();result,changed,existing=update(original.decode('utf-8'));data=result.encode('utf-8')
    report={'source':str(args.source.resolve()),'output':str(args.output.resolve()),'source_sha256':hashlib.sha256(original).hexdigest(),'output_sha256':hashlib.sha256(data).hexdigest(),'updated':changed,'already_current':existing,'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as stream:stream.write(data)
    args.output.with_suffix(args.output.suffix+'.call-boundaries.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
if __name__=='__main__':main()
