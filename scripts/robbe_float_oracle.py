"""Actual SPU helpers versus an independent exact-rational ISA value model.

IBM SPU ISA v1.2, section 9.1, FA/FS/FM/FMA/FMS/FNMS and FI.
No guest bytes, no RPCS3 implementation. Does not test FPSCR status flags.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCE='https://arcb.csc.ncsu.edu/~mueller/cluster/ps3/SDK3.0/docs/arch/SPU_ISA_v1.2_27Jan2007_pub.pdf'

def pow2(e):
    return Fraction(1 << e) if e>=0 else Fraction(1,1 << -e)

def value(raw):
    exponent=(raw >> 23) & 255
    if not exponent: return Fraction(0)
    magnitude=Fraction((raw & 0x7fffff) | 0x800000)*pow2(exponent-150)
    return -magnitude if raw >> 31 else magnitude

def pack(x):
    if not x: return 0
    sign=0x80000000 if x<0 else 0
    x=abs(x); n=x.numerator; d=x.denominator
    e=n.bit_length()-d.bit_length()
    if x < pow2(e): e-=1
    biased=e+127
    if biased<1: return 0
    if biased>255: return sign | 0x7fffffff
    mantissa=x*pow2(23-e)
    significand=mantissa.numerator // mantissa.denominator
    assert 0x800000<=significand<=0xffffff
    return sign | biased << 23 | (significand & 0x7fffff)

def reference(op,a,b,c):
    if op==7:
        assert (a & 0x7f800000)==0
        return 0
    if op==6:
        # FI's RB is packed base/step, not an ordinary float operand.
        base=1+Fraction(b & 0x7ffc00,1 << 23)
        step=Fraction(b & 0x3ff,1 << 13)
        y=Fraction(a & 0x7ffff,1 << 19)
        result=(base-step*y)*pow2(((b >> 23) & 255)-127)
        return pack(-result if b >> 31 else result)
    av,bv,cv=map(value,(a,b,c))
    return pack([lambda:av+bv,lambda:av-bv,lambda:av*bv,
                 lambda:av*bv+cv,lambda:av*bv-cv,lambda:cv-av*bv][op]())

def cases():
    rng=random.Random(0x116)
    edges=[0,0x80000000,1,0x007fffff,0x80000001,0x807fffff,
           0x00800000,0x80800000,0x00800001,0x3eaaaaab,0x3f000000,
           0x3f800000,0xbf800000,0x3f800001,0x40000000,0x7f000000,
           0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,
           0x7fb50160,0x7ff50000,0x7fffffff,0xffffffff]
    for op in range(7):
        group=[]
        for a in edges:
            for b in edges:
                group.append((a,b,edges[(edges.index(a)*7+edges.index(b)*3)%len(edges)]))
        if op in (3,4,5):
            # Non-saturated product and subnormal product must survive until add.
            group += [(0x7fffffff,0x40000000,0xffffffff),
                      (0x00800000,0x3f000000,0x00800000),
                      (0x3f800001,0x3f800001,0xbf800002)]
        if op==6:
            # All packed exponent values, both signs, base/step endpoints.
            group += [(a,(s << 31)|(e << 23)|f,0)
                      for e in range(256) for s in (0,1)
                      for f in (0,0x3ff,0x7ffc00,0x7fffff)
                      for a in (0,0x7ffff)]
        group += [(rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32)) for _ in range(4096)]
        while len(group)%4: group.append((0,0,0))
        for i in range(0,len(group),4): yield op,group[i:i+4]
    yield 7,[(0,0,0),(0x80000000,0,0),(1,0,0),(0x807fffff,0,0)]
