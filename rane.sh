#!/bin/bash

# arr=("s344" "s386" "s832" "s1494")
# arr=("s713" "s5378" "s1423")
# arr=("s13207" "s15850" "s35932" "s38417" "s38584")

arr=("s344")
key=(100 150)

for j in "${key[@]}"
do
  for i in "${arr[@]}"
  do
    echo ${i} ${j}
    python3 main_sat.py -b benchmarks/bench/original/$i.bench -o benchmarks/bench/rnd/${i}_$j.bench -t14400
  done
done
