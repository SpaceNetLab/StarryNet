import os
import threading
import sys
from time import sleep
import numpy
import subprocess

"""
Used in the remote machine for link updating, initializing links, damaging and recovering links and other functionalities。
author: Yangtao Deng (dengyt21@mails.tsinghua.edu.cn) and Zeqi Lai (zeqilai@tsinghua.edu.cn) 
"""


def sn_get_right_satellite(current_sat_id, current_orbit_id, orbit_num):
    if current_orbit_id == orbit_num - 1:
        return [current_sat_id, 0]
    else:
        return [current_sat_id, current_orbit_id + 1]


def sn_get_down_satellite(current_sat_id, current_orbit_id, sat_num):
    if current_sat_id == sat_num - 1:
        return [0, current_orbit_id]
    else:
        return [current_sat_id + 1, current_orbit_id]


def sn_ISL_establish(current_sat_id, current_orbit_id, container_id_list,
                     orbit_num, sat_num, constellation_size, matrix, bw, loss):
    current_id = current_orbit_id * sat_num + current_sat_id
    isl_idx = current_id * 2 + 1
    # Establish intra-orbit ISLs
    # (Down):
    [down_sat_id,
     down_orbit_id] = sn_get_down_satellite(current_sat_id, current_orbit_id,
                                            sat_num)
    print("[" + str(isl_idx) + "/" + str(constellation_size * 2) +
          "] Establish intra-orbit ISL from: (" + str(current_sat_id) + "," +
          str(current_orbit_id) + ") to (" + str(down_sat_id) + "," +
          str(down_orbit_id) + ")")
    ISL_name = "Le_" + str(current_sat_id) + "-" + str(current_orbit_id) + \
        "_" + str(down_sat_id) + "-" + str(down_orbit_id)
    address_16_23 = isl_idx >> 8
    address_8_15 = isl_idx & 0xff
    # Create internal network in docker.
    os.system('docker network create ' + ISL_name + " --subnet 10." +
              str(address_16_23) + "." + str(address_8_15) + ".0/24")
    print('[Create ISL:]' + 'docker network create ' + ISL_name +
          " --subnet 10." + str(address_16_23) + "." + str(address_8_15) +
          ".0/24")
    os.system('docker network connect ' + ISL_name + " " +
              str(container_id_list[current_orbit_id * sat_num +
                                    current_sat_id]) + " --ip 10." +
              str(address_16_23) + "." + str(address_8_15) + ".40")
    delay = matrix[current_orbit_id * sat_num +
                   current_sat_id][down_orbit_id * sat_num + down_sat_id]
    with os.popen(
            "docker exec -it " +
            str(container_id_list[current_orbit_id * sat_num +
                                  current_sat_id]) +
            " ip addr | grep -B 2 10." + str(address_16_23) + "." +
            str(address_8_15) +
            ".40 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]") as f:
        ifconfig_output = f.readline()
        target_interface = str(ifconfig_output).split("@")[0]
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " ip link set dev " + target_interface + " down")
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " ip link set dev " + target_interface + " name " + "B" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  "-eth" + str(down_orbit_id * sat_num + down_sat_id + 1))
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " ip link set dev B" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  "-eth" + str(down_orbit_id * sat_num + down_sat_id + 1) +
                  " up")
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " tc qdisc add dev B" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  "-eth" + str(down_orbit_id * sat_num + down_sat_id + 1) +
                  " root netem delay " + str(delay) + "ms loss " + str(loss) + "% rate " + str(bw) + "Gbit")
    print('[Add current node:]' + 'docker network connect ' + ISL_name + " " +
          str(container_id_list[current_orbit_id * sat_num + current_sat_id]) +
          " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".40")
    os.system('docker network connect ' + ISL_name + " " +
              str(container_id_list[down_orbit_id * sat_num + down_sat_id]) +
              " --ip 10." + str(address_16_23) + "." + str(address_8_15) +
              ".10")
    with os.popen(
            "docker exec -it " +
            str(container_id_list[down_orbit_id * sat_num + down_sat_id]) +
            " ip addr | grep -B 2 10." + str(address_16_23) + "." +
            str(address_8_15) +
            ".10 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]") as f:
        ifconfig_output = f.readline()
        target_interface = str(ifconfig_output).split("@")[0]
        os.system("docker exec -d " +
                  str(container_id_list[down_orbit_id * sat_num +
                                        down_sat_id]) + " ip link set dev " +
                  target_interface + " down")
        os.system("docker exec -d " +
                  str(container_id_list[down_orbit_id * sat_num +
                                        down_sat_id]) + " ip link set dev " +
                  target_interface + " name " + "B" +
                  str(down_orbit_id * sat_num + down_sat_id + 1) + "-eth" +
                  str(current_orbit_id * sat_num + current_sat_id + 1))
        os.system("docker exec -d " +
                  str(container_id_list[down_orbit_id * sat_num +
                                        down_sat_id]) + " ip link set dev B" +
                  str(down_orbit_id * sat_num + down_sat_id + 1) + "-eth" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) + " up")
        os.system("docker exec -d " +
                  str(container_id_list[down_orbit_id * sat_num +
                                        down_sat_id]) + " tc qdisc add dev B" +
                  str(down_orbit_id * sat_num + down_sat_id + 1) + "-eth" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  " root netem delay " + str(delay) + "ms loss " + str(loss) + "% rate " + str(bw) + "Gbit")
    print('[Add down node:]' + 'docker network connect ' + ISL_name + " " +
          str(container_id_list[down_orbit_id * sat_num + down_sat_id]) +
          " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".10")

    print("Add 10." + str(address_16_23) + "." + str(address_8_15) +
          ".40/24 and 10." + str(address_16_23) + "." + str(address_8_15) +
          ".10/24 to (" + str(current_sat_id) + "," + str(current_orbit_id) +
          ") to (" + str(down_sat_id) + "," + str(down_orbit_id) + ")")
    isl_idx = isl_idx + 1

    # Establish inter-orbit ISLs
    # (Right):
    [right_sat_id,
     right_orbit_id] = sn_get_right_satellite(current_sat_id, current_orbit_id,
                                              orbit_num)
    print("[" + str(isl_idx) + "/" + str(constellation_size * 2) +
          "] Establish inter-orbit ISL from: (" + str(current_sat_id) + "," +
          str(current_orbit_id) + ") to (" + str(right_sat_id) + "," +
          str(right_orbit_id) + ")")
    ISL_name = "La_" + str(current_sat_id) + "-" + str(current_orbit_id) + \
        "_" + str(right_sat_id) + "-" + str(right_orbit_id)
    address_16_23 = isl_idx >> 8
    address_8_15 = isl_idx & 0xff
    # Create internal network in docker.
    os.system('docker network create ' + ISL_name + " --subnet 10." +
              str(address_16_23) + "." + str(address_8_15) + ".0/24")
    print('[Create ISL:]' + 'docker network create ' + ISL_name +
          " --subnet 10." + str(address_16_23) + "." + str(address_8_15) +
          ".0/24")
    os.system('docker network connect ' + ISL_name + " " +
              str(container_id_list[current_orbit_id * sat_num +
                                    current_sat_id]) + " --ip 10." +
              str(address_16_23) + "." + str(address_8_15) + ".30")
    delay = matrix[current_orbit_id * sat_num +
                   current_sat_id][right_orbit_id * sat_num + right_sat_id]
    with os.popen(
            "docker exec -it " +
            str(container_id_list[current_orbit_id * sat_num +
                                  current_sat_id]) +
            " ip addr | grep -B 2 10." + str(address_16_23) + "." +
            str(address_8_15) +
            ".30 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]") as f:
        ifconfig_output = f.readline()
        target_interface = str(ifconfig_output).split("@")[0]
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " ip link set dev " + target_interface + " down")
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " ip link set dev " + target_interface + " name " + "B" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  "-eth" + str(right_orbit_id * sat_num + right_sat_id + 1))
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " ip link set dev B" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  "-eth" + str(right_orbit_id * sat_num + right_sat_id + 1) +
                  " up")
        os.system("docker exec -d " +
                  str(container_id_list[current_orbit_id * sat_num +
                                        current_sat_id]) +
                  " tc qdisc add dev B" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  "-eth" + str(right_orbit_id * sat_num + right_sat_id + 1) +
                  " root netem delay " + str(delay) + "ms loss " + str(loss) + "% rate " + str(bw) + "Gbit")
    print('[Add current node:]' + 'docker network connect ' + ISL_name + " " +
          str(container_id_list[current_orbit_id * sat_num + current_sat_id]) +
          " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".30")
    os.system('docker network connect ' + ISL_name + " " +
              str(container_id_list[right_orbit_id * sat_num + right_sat_id]) +
              " --ip 10." + str(address_16_23) + "." + str(address_8_15) +
              ".20")

    with os.popen(
            "docker exec -it " +
            str(container_id_list[right_orbit_id * sat_num + right_sat_id]) +
            " ip addr | grep -B 2 10." + str(address_16_23) + "." +
            str(address_8_15) +
            ".20 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]") as f:
        ifconfig_output = f.readline()
        target_interface = str(ifconfig_output).split("@")[0]
        os.system("docker exec -d " +
                  str(container_id_list[right_orbit_id * sat_num +
                                        right_sat_id]) + " ip link set dev " +
                  target_interface + " down")
        os.system("docker exec -d " +
                  str(container_id_list[right_orbit_id * sat_num +
                                        right_sat_id]) + " ip link set dev " +
                  target_interface + " name " + "B" +
                  str(right_orbit_id * sat_num + right_sat_id + 1) + "-eth" +
                  str(current_orbit_id * sat_num + current_sat_id + 1))
        os.system("docker exec -d " +
                  str(container_id_list[right_orbit_id * sat_num +
                                        right_sat_id]) + " ip link set dev B" +
                  str(right_orbit_id * sat_num + right_sat_id + 1) + "-eth" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) + " up")
        os.system("docker exec -d " +
                  str(container_id_list[right_orbit_id * sat_num +
                                        right_sat_id]) +
                  " tc qdisc add dev B" +
                  str(right_orbit_id * sat_num + right_sat_id + 1) + "-eth" +
                  str(current_orbit_id * sat_num + current_sat_id + 1) +
                  " root netem delay " + str(delay) + "ms loss " + str(loss) + "% rate " + str(bw) + "Gbit")
    print('[Add right node:]' + 'docker network connect ' + ISL_name + " " +
          str(container_id_list[right_orbit_id * sat_num + right_sat_id]) +
          " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".20")

    print("Add 10." + str(address_16_23) + "." + str(address_8_15) +
          ".30/24 and 10." + str(address_16_23) + "." + str(address_8_15) +
          ".20/24 to (" + str(current_sat_id) + "," + str(current_orbit_id) +
          ") to (" + str(right_sat_id) + "," + str(right_orbit_id) + ")")


def sn_establish_ISLs(container_id_list, matrix, orbit_num, sat_num,
                      constellation_size, bw, loss):
    ISL_threads = []
    for current_orbit_id in range(0, orbit_num):
        for current_sat_id in range(0, sat_num):
            ISL_thread = threading.Thread(
                target=sn_ISL_establish,
                args=(current_sat_id, current_orbit_id, container_id_list,
                      orbit_num, sat_num, constellation_size, matrix, bw,
                      loss))
            ISL_threads.append(ISL_thread)
    for ISL_thread in ISL_threads:
        ISL_thread.start()
    for ISL_thread in ISL_threads:
        ISL_thread.join()


def sn_get_param(file_):
    f = open(file_)
    ADJ = f.readlines()
    for i in range(len(ADJ)):
        ADJ[i] = ADJ[i].strip('\n')
    ADJ = [x.split(',') for x in ADJ]
    f.close()
    return ADJ


def sn_get_container_info():
    #  Read all container information in all_container_info
    with os.popen("docker ps") as f:
        all_container_info = f.readlines()
        n_container = len(all_container_info) - 1

    container_id_list = []
    for container_idx in range(1, n_container + 1):
        container_id_list.append(all_container_info[container_idx].split()[0])

    return container_id_list


def sn_establish_GSL(container_id_list, matrix, GS_num, constellation_size, bw,
                     loss):
    # starting links among satellites and ground stations
    for i in range(1, constellation_size + 1):
        for j in range(constellation_size + 1,
                       constellation_size + GS_num + 1):
            # matrix[i-1][j-1])==1 means a link between node i and node j
            if ((float(matrix[i - 1][j - 1])) <= 0.01):
                continue
            # IP address  (there is a link between i and j)
            delay = str(matrix[i - 1][j - 1])
            address_16_23 = (j - constellation_size) & 0xff
            address_8_15 = i & 0xff
            GSL_name = "GSL_" + str(i) + "-" + str(j)
            # Create internal network in docker.
            os.system('docker network create ' + GSL_name + " --subnet 9." +
                      str(address_16_23) + "." + str(address_8_15) + ".0/24")
            print('[Create GSL:]' + 'docker network create ' + GSL_name +
                  " --subnet 9." + str(address_16_23) + "." +
                  str(address_8_15) + ".0/24")
            os.system('docker network connect ' + GSL_name + " " +
                      str(container_id_list[i - 1]) + " --ip 9." +
                      str(address_16_23) + "." + str(address_8_15) + ".50")
            with os.popen(
                    "docker exec -it " + str(container_id_list[i - 1]) +
                    " ip addr | grep -B 2 9." + str(address_16_23) + "." +
                    str(address_8_15) +
                    ".50 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]"
            ) as f:
                ifconfig_output = f.readline()
                target_interface = str(ifconfig_output).split("@")[0]
                os.system("docker exec -d " + str(container_id_list[i - 1]) +
                          " ip link set dev " + target_interface + " down")
                os.system("docker exec -d " + str(container_id_list[i - 1]) +
                          " ip link set dev " + target_interface + " name " +
                          "B" + str(i - 1 + 1) + "-eth" + str(j))
                os.system("docker exec -d " + str(container_id_list[i - 1]) +
                          " ip link set dev B" + str(i - 1 + 1) + "-eth" +
                          str(j) + " up")
                os.system("docker exec -d " + str(container_id_list[i - 1]) +
                          " tc qdisc add dev B" + str(i - 1 + 1) + "-eth" +
                          str(j) + " root netem delay " + str(delay) + "ms loss " + str(loss) + "% rate " + str(bw) + "Gbit")
            print('[Add current node:]' + 'docker network connect ' +
                  GSL_name + " " + str(container_id_list[i - 1]) + " --ip 9." +
                  str(address_16_23) + "." + str(address_8_15) + ".50")

            os.system('docker network connect ' + GSL_name + " " +
                      str(container_id_list[j - 1]) + " --ip 9." +
                      str(address_16_23) + "." + str(address_8_15) + ".60")
            with os.popen(
                    "docker exec -it " + str(container_id_list[j - 1]) +
                    " ip addr | grep -B 2 9." + str(address_16_23) + "." +
                    str(address_8_15) +
                    ".60 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]"
            ) as f:
                ifconfig_output = f.readline()
                target_interface = str(ifconfig_output).split("@")[0]
                os.system("docker exec -d " + str(container_id_list[j - 1]) +
                          " ip link set dev " + target_interface + " down")
                os.system("docker exec -d " + str(container_id_list[j - 1]) +
                          " ip link set dev " + target_interface + " name " +
                          "B" + str(j) + "-eth" + str(i - 1 + 1))
                os.system("docker exec -d " + str(container_id_list[j - 1]) +
                          " ip link set dev B" + str(j) + "-eth" +
                          str(i - 1 + 1) + " up")
                os.system("docker exec -d " + str(container_id_list[j - 1]) +
                          " tc qdisc add dev B" + str(j) + "-eth" +
                          str(i - 1 + 1) + " root netem delay " + str(delay) +
                          "ms loss " + str(loss) + "% rate " + str(bw) +
                          "Gbit")
            print('[Add right node:]' + 'docker network connect ' + GSL_name +
                  " " + str(container_id_list[j - 1]) + " --ip 9." +
                  str(address_16_23) + "." + str(address_8_15) + ".60")
    for j in range(constellation_size + 1, constellation_size + GS_num + 1):
        GS_name = "GS_" + str(j)
        # Create default network and interface for GS.
        os.system('docker network create ' + GS_name + " --subnet 9." +
                  str(j) + "." + str(j) + ".0/24")
        print('[Create GS network:]' + 'docker network create ' + GS_name +
              " --subnet 9." + str(j) + "." + str(j) + ".10/24")
        os.system('docker network connect ' + GS_name + " " +
                  str(container_id_list[j - 1]) + " --ip 9." + str(j) + "." +
                  str(j) + ".10")
        with os.popen(
                "docker exec -it " + str(container_id_list[j - 1]) +
                " ip addr | grep -B 2 9." + str(j) + "." + str(j) +
                ".10 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]"
        ) as f:
            ifconfig_output = f.readline()
            target_interface = str(ifconfig_output).split("@")[0]
            os.system("docker exec -d " + str(container_id_list[j - 1]) +
                      " ip link set dev " + target_interface + " down")
            os.system("docker exec -d " + str(container_id_list[j - 1]) +
                      " ip link set dev " + target_interface + " name " + "B" +
                      str(j - 1 + 1) + "-default")
            os.system("docker exec -d " + str(container_id_list[j - 1]) +
                      " ip link set dev B" + str(j - 1 + 1) + "-default" +
                      " up")
        print('[Add current node:]' + 'docker network connect ' + GS_name +
              " " + str(container_id_list[j - 1]) + " --ip 9." + str(j) + "." +
              str(j) + ".10")


def sn_copy_run_conf(container_idx, Path, current, total):
    os.system("docker cp " + Path + "/B" + str(current + 1) + ".conf " +
              str(container_idx) + ":/B" + str(current + 1) + ".conf")
    print("[" + str(current + 1) + "/" + str(total) + "]" +
          " docker cp bird.conf " + str(container_idx) + ":/bird.conf")
    #os.system("docker exec -it " + str(container_idx) + " bird -c B" +
    #          str(current + 1) + ".conf")
    result = subprocess.run(["docker", "exec", str(container_idx), "bird", "-c", "B"+str(current+1)+".conf"],
                            capture_output=True, text=True)
    with open("/tmp/bird.log", "a") as f:
        f.write(str(container_idx)+": "+result.stdout+"\n")
    print("[" + str(current + 1) + "/" + str(total) +
          "] Bird routing process for container: " + str(container_idx) +
          " has started. ")


def sn_copy_run_conf_to_each_container(container_id_list, sat_node_number,
                                       fac_node_number, path):
    print(
        "Copy bird configuration file to each container and run routing process."
    )
    total = len(container_id_list)
    copy_threads = []
    for current in range(0, total):
        copy_thread = threading.Thread(
            target=sn_copy_run_conf,
            args=(container_id_list[current], path + "/conf/bird-" +
                  str(sat_node_number) + "-" + str(fac_node_number), current,
                  total))
        copy_threads.append(copy_thread)
    for copy_thread in copy_threads:
        copy_thread.start()
    for copy_thread in copy_threads:
        copy_thread.join()
    print("Initializing routing...")
    sleep(120)
    print("Routing initialized!")


def sn_damage_link(sat_index, container_id_list):
    with os.popen(
            "docker exec -it " + str(container_id_list[sat_index]) +
            " ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'") as f:
        ifconfig_output = f.readlines()
        for intreface in range(0, len(ifconfig_output), 2):
            os.system("docker exec -d " + str(container_id_list[sat_index]) +
                      " tc qdisc change dev " +
                      ifconfig_output[intreface][:-1] +
                      " root netem loss 100%")
            print("docker exec -d " + str(container_id_list[sat_index]) +
                  " tc qdisc change dev " + ifconfig_output[intreface][:-1] +
                  " root netem loss 100%")


def sn_damage(random_list, container_id_list):
    damage_threads = []
    for random_satellite in random_list:
        damage_thread = threading.Thread(target=sn_damage_link,
                                         args=(int(random_satellite),
                                               container_id_list))
        damage_threads.append(damage_thread)
    for damage_thread in damage_threads:
        damage_thread.start()
    for damage_thread in damage_threads:
        damage_thread.join()


def sn_recover_link(
    damaged_satellite,
    container_id_list,
    sat_loss,
):
    with os.popen(
            "docker exec -it " + str(container_id_list[damaged_satellite]) +
            " ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'") as f:
        ifconfig_output = f.readlines()
        for i in range(0, len(ifconfig_output), 2):
            os.system("docker exec -d " +
                      str(container_id_list[damaged_satellite]) +
                      " tc qdisc change dev " + ifconfig_output[i][:-1] +
                      " root netem loss " + str(sat_loss) + "%")
            print("docker exec -d " +
                  str(container_id_list[damaged_satellite]) +
                  " tc qdisc change dev " + ifconfig_output[i][:-1] +
                  " root netem loss " + str(sat_loss) + "%")


def sn_del_network(network_name):
    os.system('docker network rm ' + network_name)


def sn_stop_emulation():
    os.system("docker service rm constellation-test")
    with os.popen("docker rm -f $(docker ps -a -q)") as f:
        f.readlines()
    with os.popen("docker network ls") as f:
        all_br_info = f.readlines()
        del_threads = []
        for line in all_br_info:
            if "La" in line or "Le" or "GS" in line:
                network_name = line.split()[1]
                del_thread = threading.Thread(target=sn_del_network,
                                              args=(network_name, ))
                del_threads.append(del_thread)
        for del_thread in del_threads:
            del_thread.start()
        for del_thread in del_threads:
            del_thread.join()


def sn_recover(damage_list, container_id_list, sat_loss):
    recover_threads = []
    for damaged_satellite in damage_list:
        recover_thread = threading.Thread(target=sn_recover_link,
                                          args=(int(damaged_satellite),
                                                container_id_list, sat_loss))
        recover_threads.append(recover_thread)
    for recover_thread in recover_threads:
        recover_thread.start()
    for recover_thread in recover_threads:
        recover_thread.join()


def sn_update_delay(matrix, container_id_list,
                    constellation_size):  # updating delays
    delay_threads = []
    for row in range(len(matrix)):
        for col in range(row, len(matrix[row])):
            if float(matrix[row][col]) > 0:
                if row < col:
                    delay_thread = threading.Thread(
                        target=sn_delay_change,
                        args=(row, col, matrix[row][col], container_id_list,
                              constellation_size))
                    delay_threads.append(delay_thread)
                else:
                    delay_thread = threading.Thread(
                        target=sn_delay_change,
                        args=(col, row, matrix[col][row], container_id_list,
                              constellation_size))
                    delay_threads.append(delay_thread)
    for delay_thread in delay_threads:
        delay_thread.start()
    for delay_thread in delay_threads:
        delay_thread.join()
    print("Delay updating done.\n")


def sn_delay_change(link_x, link_y, delay, container_id_list,
                    constellation_size):  # multi-thread updating delays
    if link_y <= constellation_size:
        os.system("docker exec -d " + str(container_id_list[link_x]) +
                  " tc qdisc change dev B" + str(link_x + 1) + "-eth" +
                  str(link_y + 1) + " root netem delay " + str(delay) + "ms")
        os.system("docker exec -d " + str(container_id_list[link_y]) +
                  " tc qdisc change dev B" + str(link_y + 1) + "-eth" +
                  str(link_x + 1) + " root netem delay " + str(delay) + "ms")
    else:
        os.system("docker exec -d " + str(container_id_list[link_x]) +
                  " tc qdisc change dev B" + str(link_x + 1) + "-eth" +
                  str(link_y + 1) + " root netem delay " + str(delay) + "ms")
        os.system("docker exec -d " + str(container_id_list[link_y]) +
                  " tc qdisc change dev B" + str(link_y + 1) + "-eth" +
                  str(link_x + 1) + " root netem delay " + str(delay) + "ms")


if __name__ == '__main__':
    if len(sys.argv) == 10:
        orbit_num = int(sys.argv[1])
        sat_num = int(sys.argv[2])
        constellation_size = int(sys.argv[3])
        GS_num = int(sys.argv[4])
        sat_bandwidth = float(sys.argv[5])
        sat_loss = float(sys.argv[6])
        sat_ground_bandwidth = float(sys.argv[7])
        sat_ground_loss = float(sys.argv[8])
        current_topo_path = sys.argv[9]
        matrix = sn_get_param(current_topo_path)
        container_id_list = sn_get_container_info()
        sn_establish_ISLs(container_id_list, matrix, orbit_num, sat_num,
                          constellation_size, sat_bandwidth, sat_loss)
        sn_establish_GSL(container_id_list, matrix, GS_num, constellation_size,
                         sat_ground_bandwidth, sat_ground_loss)
    elif len(sys.argv) == 4:
        if sys.argv[3] == "update":
            current_delay_path = sys.argv[1]
            constellation_size = int(sys.argv[2])
            matrix = sn_get_param(current_delay_path)
            container_id_list = sn_get_container_info()
            sn_update_delay(matrix, container_id_list, constellation_size)
        else:
            constellation_size = int(sys.argv[1])
            GS_num = int(sys.argv[2])
            path = sys.argv[3]
            container_id_list = sn_get_container_info()
            sn_copy_run_conf_to_each_container(container_id_list,
                                               constellation_size, GS_num,
                                               path)
    elif len(sys.argv) == 2:
        path = sys.argv[1]
        random_list = numpy.loadtxt(path + "/damage_list.txt")
        container_id_list = sn_get_container_info()
        sn_damage(random_list, container_id_list)
    elif len(sys.argv) == 3:
        path = sys.argv[1]
        sat_loss = float(sys.argv[2])
        damage_list = numpy.loadtxt(path + "/damage_list.txt")
        container_id_list = sn_get_container_info()
        sn_recover(damage_list, container_id_list, sat_loss)
    elif len(sys.argv) == 1:
        sn_stop_emulation()
