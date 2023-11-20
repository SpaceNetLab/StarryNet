import os
import glob
import json
import argparse
import paramiko
import numpy
import random

def sn_load_file(path, GS_lat_long):
    f = open(path, 'r', encoding='utf8')
    table = json.load(f)
    parser = argparse.ArgumentParser(description='manual to this script')
    parser.add_argument('--cons_name', type=str, default=table['Name'])
    parser.add_argument('--link_style', type=str, default=table['Satellite link'])
    parser.add_argument('--IP_version', type=str, default=table['IP version'])
    parser.add_argument('--link_policy', type=str, default=table['Link policy'])
    # link delay updating granularity
    parser.add_argument('--update_interval',
                        type=int,
                        default=table['update_time (s)'])
    parser.add_argument('--duration', type=int, default=table['Duration (s)'])
    parser.add_argument('--sat_bandwidth',
                        type=int,
                        default=table['satellite link bandwidth ("X" Gbps)'])
    parser.add_argument('--sat_ground_bandwidth',
                        type=int,
                        default=table['sat-ground bandwidth ("X" Gbps)'])
    parser.add_argument('--sat_loss',
                        type=int,
                        default=table['satellite link loss ("X"% )'])
    parser.add_argument('--sat_ground_loss',
                        type=int,
                        default=table['sat-ground loss ("X"% )'])
    parser.add_argument('--antenna_number',
                        type=int,
                        default=table['antenna number'])
    parser.add_argument('--antenna_elevation',
                        type=int,
                        default=table['antenna elevation angle'])
    # TODO: parser.add_argument('--handover', default=table["Handover policy"])
    # TODO: parser.add_argument('--time_slot', type=int, default=100)
    # TODO: parser.add_argument('--user_num', type=int, default=0)
    sn_args = parser.parse_args()
    sn_args.__setattr__('machine_lst', table['Machines'])
    shell_lst = [{
        'altitude': shell['Altitude (km)'],
        'inclination': shell['Inclination'],
        'phase_shift': shell['Phase shift'],
        'orbit': shell['Orbits'],
        'sat': shell['Satellites per orbit'],
        } for shell in table["Shells"]]
    sn_args.__setattr__('shell_lst', shell_lst)
    return sn_args

def sn_connect_remote(host, port, username, password):
    remote_ssh = paramiko.SSHClient()
    remote_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    remote_ssh.connect(hostname=host, port=port, username=username, password=password)
    return remote_ssh, remote_ssh.open_sftp()

def sn_remote_cmd(remote_ssh, cmd):
    return remote_ssh.exec_command(cmd)[1].read().decode().strip()

def sn_remote_wait_output(remote_ssh, cmd):
    for line in remote_ssh.exec_command(cmd, get_pty=True)[1]:
        print(line, end='')

def sn_check_utility(time_index, remote_ssh, local_dir):
    result = sn_remote_cmd(remote_ssh, "vmstat")
    f = open(os.path.join(local_dir, f"utility-info_{time_index}.txt"), "w")
    f.write(result)
    f.close()

def sn_update_delay(remote_ssh, remote_ftp, remote_dir, local_dir,
                    timeptr, constellation_size):
    remote_ftp.put(
        os.path.join(local_dir, 'delay',  f'{timeptr}.txt.gz'),
        f'{remote_dir}/{timeptr}.txt.gz')
    sn_remote_cmd(remote_ssh,
        f"python3 {remote_dir}/orchestrater.py "
        f"{remote_dir}/{timeptr}.txt.gz {constellation_size} update")
    print("Delay updating done.")

def sn_damage(remote_ssh, remote_ftp, remote_dir, local_dir,
              ratio, damage_list, constellation_size):
    print("Randomly setting damaged links...\n")
    cumulated_damage_list = damage_list
    random_list = [
        random.randint(0, constellation_size - 1) 
        for _ in range(int(constellation_size * ratio))
    ]
    cumulated_damage_list.extend(random_list)
    list_file = os.path.join(local_dir, 'mid_files', 'damage_list.txt')
    numpy.savetxt(list_file, random_list)
    remote_ftp.put(list_file, f'{remote_dir}/damage_list.txt')
    sn_remote_cmd(remote_ssh, f"python3 {remote_dir}/orchestrater.py {remote_dir}")
    print("Damage done.\n")


def sn_recover(remote_ssh, remote_ftp, remote_dir, local_dir, damage_list, sat_loss):
    print("Recovering damaged links...\n")
    list_file = os.path.join(local_dir, 'mid_files', 'damage_list.txt')
    numpy.savetxt(list_file, damage_list)
    remote_ftp.put(list_file, f'{remote_dir}/damage_list.txt')
    sn_remote_cmd(remote_ssh, 
        f"python3 {remote_dir}/orchestrater.py {remote_dir} {sat_loss}"
    )
    damage_list.clear()
    print("Link recover done.\n")

def sn_sr(src, des, target, netns_list, remote_ssh):
    ifconfig_output = sn_remote_cmd(remote_ssh, 
        f"ip netns exec {netns_list[des - 1]} "
        r"ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'").splitlines()
    des_IP = sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[des - 1]} ifconfig {ifconfig_output[0][:-1]} " 
        "| awk -F '[ :]+' 'NR==2{print $4}'").splitlines()
    target_IP = sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[target - 1]} ifconfig B{target}-eth{src} "
        "| awk -F '[ :]+' 'NR==2{print $4}'").splitlines()
    sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[src - 1]} "
        f" ip route del {des_IP[0][:-3]}0/24")
    sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[src - 1]} "
        f"ip route add {des_IP[0][:-3]}0/24 dev B{src}-eth{target} via {target_IP[0]}")
    print(
        f"ip netns exec {netns_list[src - 1]} "
        f"ip route add {des_IP[0][:-3]}0/24 dev B{src}-eth{target} via {target_IP[0]}"
    )

def sn_ping(src, des, time_index, constellation_size, container_id_list,
            file_path, configuration_file_path, remote_ssh):
    if des <= constellation_size:
        ifconfig_output = sn_remote_cmd(remote_ssh,
            f"ip netns exec {container_id_list[des - 1]} "
            r"ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'")
        des_IP = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig " + ifconfig_output[0][:-1] +
            "|awk -F '[ :]+' 'NR==2{print $4}'")
    else:
        des_IP = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig B" + str(des) +
            "-default |awk -F '[ :]+' 'NR==2{print $4}'")
    ping_result = sn_remote_cmd(
        remote_ssh, "docker exec -i " + str(container_id_list[src - 1]) +
        " ping " + str(des_IP[0][:-1]) + " -c 4 -i 0.01 ")
    f = open(
        configuration_file_path + "/" + file_path + "/ping-" + str(src) + "-" +
        str(des) + "_" + str(time_index) + ".txt", "w")
    f.writelines(ping_result)
    f.close()


def sn_perf(src, des, time_index, constellation_size, container_id_list,
            file_path, configuration_file_path, remote_ssh):
    if des <= constellation_size:
        ifconfig_output = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'")
        des_IP = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig " + ifconfig_output[0][:-1] +
            "|awk -F '[ :]+' 'NR==2{print $4}'")
    else:
        des_IP = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig B" + str(des) +
            "-default |awk -F '[ :]+' 'NR==2{print $4}'")
    print('<>', src, des, des_IP)
    sn_remote_cmd(
        remote_ssh,
        "docker exec -id " + str(container_id_list[des - 1]) + " iperf3 -s ")
    print("iperf server success")
    perf_result = sn_remote_cmd(
        remote_ssh, "docker exec -i " + str(container_id_list[src - 1]) +
        " iperf3 -c " + str(des_IP[0][:-1]) + " -t 5 ")
    print("iperf client success")
    f = open(
        configuration_file_path + "/" + file_path + "/perf-" + str(src) + "-" +
        str(des) + "_" + str(time_index) + ".txt", "w")
    f.writelines(perf_result)
    f.close()

def sn_route(src, time_index, file_path, configuration_file_path,
             container_id_list, remote_ssh):
    route_result = sn_remote_cmd(
        remote_ssh,
        "docker exec -it " + str(container_id_list[src - 1]) + " route ")
    f = open(
        configuration_file_path + "/" + file_path + "/route-" + str(src) +
        "_" + str(time_index) + ".txt", "w")
    f.writelines(route_result)
    f.close()


def sn_establish_new_GSL(container_id_list, matrix, constellation_size, bw,
                         loss, sat_index, GS_index, remote_ssh):
    i = sat_index
    j = GS_index
    # IP address  (there is a link between i and j)
    delay = str(matrix[i - 1][j - 1])
    address_16_23 = (j - constellation_size) & 0xff
    address_8_15 = i & 0xff
    GSL_name = "GSL_" + str(i) + "-" + str(j)
    # Create internal network in docker.
    sn_remote_cmd(
        remote_ssh, 'docker network create ' + GSL_name + " --subnet 9." +
        str(address_16_23) + "." + str(address_8_15) + ".0/24")
    print('[Create GSL:]' + 'docker network create ' + GSL_name +
          " --subnet 9." + str(address_16_23) + "." + str(address_8_15) +
          ".0/24")
    sn_remote_cmd(
        remote_ssh, 'docker network connect ' + GSL_name + " " +
        str(container_id_list[i - 1]) + " --ip 9." + str(address_16_23) + "." +
        str(address_8_15) + ".50")
    ifconfig_output = sn_remote_cmd(
        remote_ssh, "docker exec -it " + str(container_id_list[i - 1]) +
        " ip addr | grep -B 2 9." + str(address_16_23) + "." +
        str(address_8_15) +
        ".50 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]")
    target_interface = str(ifconfig_output[0]).split("@")[0]
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[i - 1]) +
        " ip link set dev " + target_interface + " down")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[i - 1]) +
        " ip link set dev " + target_interface + " name " + "B" +
        str(i - 1 + 1) + "-eth" + str(j))
    
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[i - 1]) +
        " tc qdisc add dev B" + str(i - 1 + 1) + "-eth" + str(j) +
        " root netem delay " + str(delay) + "ms")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[i - 1]) +
        " tc qdisc add dev B" + str(i - 1 + 1) + "-eth" + str(j) +
        " root netem loss " + str(loss) + "%")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[i - 1]) +
        " tc qdisc add dev B" + str(i - 1 + 1) + "-eth" + str(j) +
        " root netem rate " + str(bw) + "Gbps")
    print('[Add current node:]' + 'docker network connect ' + GSL_name + " " +
          str(container_id_list[i - 1]) + " --ip 9." + str(address_16_23) +
          "." + str(address_8_15) + ".50")
    print(sn_remote_cmd(
        remote_ssh, 'docker network connect ' + GSL_name + " " +
        str(container_id_list[j - 1]) + " --ip 9." + str(address_16_23) + "." +
        str(address_8_15) + ".60"))
    ifconfig_output = sn_remote_cmd(
        remote_ssh, "docker exec -it " + str(container_id_list[j - 1]) +
        " ip addr | grep -B 2 9." + str(address_16_23) + "." +
        str(address_8_15) +
        ".60 | head -n 1 | awk -F: '{ print $2 }' | tr -d [:blank:]")
    print(ifconfig_output)
    target_interface = str(ifconfig_output[0]).split("@")[0]
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[j - 1]) +
        " ip link set dev " + target_interface + " down")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[j - 1]) +
        " ip link set dev " + target_interface + " name " + "B" + str(j) +
        "-eth" + str(i - 1 + 1))
    
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[j - 1]) +
        " tc qdisc add dev B" + str(j) + "-eth" + str(i - 1 + 1) +
        " root netem delay " + str(delay) + "ms")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[j - 1]) +
        " tc qdisc add dev B" + str(j) + "-eth" + str(i - 1 + 1) +
        " root netem loss " + str(loss) + "%")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[j - 1]) +
        " tc qdisc add dev B" + str(j) + "-eth" + str(i - 1 + 1) +
        " root netem rate " + str(bw) + "Gbps")
    print('[Add right node:]' + 'docker network connect ' + GSL_name + " " +
          str(container_id_list[j - 1]) + " --ip 10." + str(address_16_23) +
          "." + str(address_8_15) + ".60")
    
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[i - 1]) +
        " ip link set dev B" + str(i - 1 + 1) + "-eth" + str(j) + " up")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " + str(container_id_list[j - 1]) +
        " ip link set dev B" + str(j) + "-eth" + str(i - 1 + 1) + " up")


def sn_del_link(first_index, second_index, container_id_list, remote_ssh):
    sn_remote_cmd(
        remote_ssh, "docker exec -d " +
        str(container_id_list[second_index - 1]) + " ip link set dev B" +
        str(second_index) + "-eth" + str(first_index) + " down")
    sn_remote_cmd(
        remote_ssh, "docker exec -d " +
        str(container_id_list[first_index - 1]) + " ip link set dev B" +
        str(first_index) + "-eth" + str(second_index) + " down")
    GSL_name = "GSL_" + str(first_index) + "-" + str(second_index)
    sn_remote_cmd(
        remote_ssh, 'docker network disconnect ' + GSL_name + " " +
        str(container_id_list[first_index - 1]))
    sn_remote_cmd(
        remote_ssh, 'docker network disconnect ' + GSL_name + " " +
        str(container_id_list[second_index - 1]))
    sn_remote_cmd(remote_ssh, 'docker network rm ' + GSL_name)