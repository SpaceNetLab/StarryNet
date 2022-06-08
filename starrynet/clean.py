#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Starrynet Cleanup
author: Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""
import os


def cleanup():
    print("Deleting all native bridges and containers...")
    #os.system("FOR /f \"tokens=*\" %i IN ('docker ps -q') DO docker stop %i")
    os.system("docker service rm constellation-test")
    with os.popen("docker rm -f $(docker ps -a -q)") as f:
        f.readlines()
    with os.popen("docker network ls") as f:
        all_br_info = f.readlines()
        for line in all_br_info:
            if "La" in line or "Le" or "GS" in line:
                network_name = line.split()[1]
                print('docker network rm ' + network_name)
                os.system('docker network rm ' + network_name)


if __name__ == "__main__":
    cleanup()