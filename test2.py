# -*- coding: utf-8 -*-
"""
Created on Fri May  8 10:58:52 2026

@author: Mohammadali
"""

from swmmx import swmm
import numpy as np
import pandas as df

path = 'example/example.inp'

m = swmm(path)

a1 = m.time.count()
#a2 = m.time.count_run()

a3 = m.time.vector()
#a4 = m.time.vector_run()

val = m.validate()

m.run()

#m.plot.network()

b1 = m.time.count()
b2 = m.time.count_run()

b3 = m.time.vector()
b4 = m.time.vector_run()


log = m.log()
