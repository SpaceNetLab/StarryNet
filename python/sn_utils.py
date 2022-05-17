import os
import paramiko
import requests
import threading


def sn_get_left_satellite(current_sat_id, current_orbit_id, orbit_num):
    if current_orbit_id == 0:
        return [current_sat_id, orbit_num-1]
    else:
        return [current_sat_id, current_orbit_id -1]


def sn_get_right_satellite(current_sat_id, current_orbit_id, orbit_num):
    if current_orbit_id == orbit_num -1:
        return [current_sat_id, 0]
    else:
        return [current_sat_id, current_orbit_id + 1]


def sn_get_up_satellite(current_sat_id, current_orbit_id, sat_num):
    if current_sat_id == 0:
        return [sat_num - 1, current_orbit_id]
    else:
        return [current_sat_id - 1, current_orbit_id, ]


def sn_get_down_satellite(current_sat_id, current_orbit_id, sat_num):
    if current_sat_id == sat_num - 1:
        return [0, current_orbit_id]
    else:
        return [current_sat_id + 1, current_orbit_id]


def sn_rename_all_container(remote_ssh, container_id_list, container_global_idx):
    print("Rename all containers ...")
    for container_id in container_id_list:
        print(sn_remote_cmd(remote_ssh, "docker rename " + str(container_id) + " ovs_container_" + str(container_global_idx)))
        container_global_idx = container_global_idx + 1


def sn_delete_remote_network_bridge(remote_machine_ssh):
    all_br_info = sn_remote_cmd(remote_machine_ssh, "docker network ls")
    for line in all_br_info:
        if "La" in line or "Le" in line:
            network_name = line.split()[1]
            print('docker network rm ' + network_name)
            sn_remote_cmd(remote_machine_ssh, 'docker network rm ' + network_name)

def sn_reset_docker_env(remote_machine_ssh, docker_service_name, constellation_size):
    print("Reset docker environment for constellation emulation ...")
    print(sn_remote_cmd(remote_machine_ssh, "docker service rm " + docker_service_name))
    print(sn_remote_cmd(remote_machine_ssh, "docker rm -f $(docker ps -a -q)"))
    print(sn_remote_cmd(remote_machine_ssh, "docker service create --replicas " + str(constellation_size) + " --name " + str(docker_service_name) + " --cap-add ALL lzq8272587/starlab_node ping www.baidu.com"))
    sn_delete_remote_network_bridge(remote_machine_ssh)



def sn_init_remote_machine(host, username, password):
    remote_machine_ssh = paramiko.SSHClient()
    remote_machine_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    remote_machine_ssh.connect(hostname=host, port=22, username=username, password=password)
    return remote_machine_ssh


def sn_local_cmd(cmd):
    os.system(cmd)


def sn_remote_cmd(remote_ssh, cmd):
    stdin, stdout, stderr = remote_ssh.exec_command(cmd)
    return stdout.readlines()


def sn_get_remote_container_info(remote_machine_ssh):
    all_container_info = sn_remote_cmd(remote_machine_ssh, "docker ps")
    n_container = len(all_container_info) - 1

    container_id_list = []
    for container_idx in range(1, n_container + 1):
        # print(all_container_info[container_idx])
        # print(all_container_info[container_idx].split()[0])
        container_id_list.append(all_container_info[container_idx].split()[0])

    return container_id_list


def sn_establish_intra_ISL_native(remote_machine_ssh, container_id_list, orbit_num, sat_num, constellation_size, isl_idx):
    # Establish intra-orbit ISLs
    for current_orbit_id in range(0, orbit_num):
        for current_sat_id in range(0, sat_num):
            # (Down):
            [down_sat_id, down_orbit_id] = sn_get_down_satellite(current_sat_id, current_orbit_id, sat_num)
            print("[" + str(isl_idx) + "/" + str(constellation_size * 4) + "] Establish intra-orbit ISL from: (" + str(current_sat_id) + "," + str(current_orbit_id) + ") to (" + str(down_sat_id) + "," + str(down_orbit_id) + ")")
            #print("ovs-vsctl add-br ISL_" + str(current_sat_id) + "-" + str(current_orbit_id) + "_" + str(down_sat_id) + "-" + str(down_orbit_id) )
            ISL_name = "La_" + str(current_sat_id) + "-" + str(current_orbit_id) + "_" + str(down_sat_id) + "-" + str(down_orbit_id)
            address_16_23 = isl_idx >> 8
            address_8_15 = isl_idx & 0xff
            # Create internal network in docker.
            sn_remote_cmd(remote_machine_ssh, 'docker network create ' + ISL_name + " --subnet 10." + str(address_16_23) + "." + str(address_8_15) + ".0/24")
            print('[Create ISL:]' + 'docker network create ' + ISL_name + " --subnet 10." + str(address_16_23) + "." + str(address_8_15) + ".0/24")
            sn_remote_cmd(remote_machine_ssh, 'docker network connect ' + ISL_name + " " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".40")
            print('[Add current node:]' + 'docker network connect ' + ISL_name + " " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".40")
            sn_remote_cmd(remote_machine_ssh, 'docker network connect ' + ISL_name + " " + str(container_id_list[down_orbit_id * sat_num + down_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".10")
            print('[Add down node:]' + 'docker network connect ' + ISL_name + " " + str(container_id_list[down_orbit_id * sat_num + down_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".10")

            #os.system("ovs-docker add-port " + str(ISL_hub) + " ISL_down " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ipaddress=10." + str(address_16_23) + "." + str(address_8_15) + ".4/24" )
            #os.system("ovs-docker add-port " + str(ISL_hub) + " ISL_up " + str(container_id_list[down_orbit_id * sat_num + down_sat_id]) + " --ipaddress=10." + str(address_16_23) + "." + str(address_8_15) + ".1/24")
            #os.system("ovs-docker set-vlan " + str(ISL_hub) + " ISL_down " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " " + str(isl_idx)) # ovs-docker set-vlan br0 eth1 ovs_container_1 100
            #os.system("ovs-docker set-vlan " + str(ISL_hub) + " ISL_up " + str(container_id_list[down_orbit_id * sat_num + down_sat_id]) + " " + str(isl_idx))

            # os.system("ovs-docker add-port " + ISL_name + " ISL_down " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ipaddress=10." + str(current_orbit_id) + "." + str(current_sat_id) + ".4/24" )
            # os.system("ovs-docker add-port " + ISL_name + " ISL_up " + str( container_id_list[current_orbit_id * sat_num + down_sat_id]) + " --ipaddress=10." + str(current_orbit_id) + "." + str(down_sat_id) + ".1/24")
            print("Add 10." + str(address_16_23) + "." + str(address_8_15) + ".40/24 and 10." + str(address_16_23) + "." + str(address_8_15) + ".10/24 to (" + str(current_sat_id) + "," + str(current_orbit_id) + ") to (" + str(down_sat_id) + "," + str(down_orbit_id) + ")")
            isl_idx = isl_idx + 1


def sn_establish_inter_ISL_native(remote_machine_ssh, container_id_list, orbit_num, sat_num, constellation_size, isl_idx):
    # Establish inter-orbit ISLs
    for current_orbit_id in range(0, orbit_num):
        for current_sat_id in range(0, sat_num):
            # (Right):
            [right_sat_id, right_orbit_id] = sn_get_right_satellite(current_sat_id, current_orbit_id, orbit_num)
            print("[" + str(isl_idx) + "/" + str(constellation_size*2) + "] Establish inter-orbit ISL from: (" + str(current_sat_id) + "," + str(current_orbit_id) + ") to (" + str(right_sat_id) + "," + str(right_orbit_id) + ")")
            #print("ovs-vsctl add-br ISL_" + str(current_sat_id) + "-" + str(current_orbit_id) + "_" + str(right_sat_id) + "-" + str(right_orbit_id))
            ISL_name = "Le_" + str(current_sat_id) + "-" + str(current_orbit_id) + "_" + str(right_sat_id) + "-" + str(right_orbit_id)
            address_16_23 = isl_idx >> 8
            address_8_15 = isl_idx & 0xff
            # Create internal network in docker.
            sn_remote_cmd(remote_machine_ssh, 'docker network create ' + ISL_name + " --subnet 10." + str(address_16_23) + "." + str(address_8_15) + ".0/24")
            print('[Create ISL:]' + 'docker network create ' + ISL_name + " --subnet 10." + str(address_16_23) + "." + str(address_8_15) + ".0/24")
            sn_remote_cmd(remote_machine_ssh, 'docker network connect ' + ISL_name + " " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".30")
            print('[Add current node:]' + 'docker network connect ' + ISL_name + " " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".30")
            sn_remote_cmd(remote_machine_ssh, 'docker network connect ' + ISL_name + " " + str(container_id_list[right_orbit_id * sat_num + right_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".20")
            print('[Add right node:]' + 'docker network connect ' + ISL_name + " " + str(container_id_list[right_orbit_id * sat_num + right_sat_id]) + " --ip 10." + str(address_16_23) + "." + str(address_8_15) + ".20")

            #os.system("ovs-docker add-port " + str(ISL_hub) + " ISL_right " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ipaddress=10." + str(address_16_23) + "." + str(address_8_15) + ".3/24" )
            #os.system("ovs-docker add-port " + str(ISL_hub) + " ISL_left " + str(container_id_list[right_orbit_id * sat_num + right_sat_id]) + " --ipaddress=10." + str(address_16_23) + "." + str(address_8_15) + ".2/24")
            #os.system("ovs-docker set-vlan " + str(ISL_hub) + " ISL_right " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " " + str(isl_idx))
            #os.system("ovs-docker set-vlan " + str(ISL_hub) + " ISL_left " + str(container_id_list[right_orbit_id * sat_num + right_sat_id]) + " " + str(isl_idx))

            # os.system("ovs-docker add-port " + ISL_name + " ISL_right " + str(container_id_list[current_orbit_id * sat_num + current_sat_id]) + " --ipaddress=10." + str(current_orbit_id) + "." + str(current_sat_id) + ".3/24" )
            # os.system("ovs-docker add-port " + ISL_name + " ISL_left " + str(container_id_list[right_orbit_id * sat_num + right_sat_id]) + " --ipaddress=10." + str(right_orbit_id) + "." + str(right_sat_id) + ".2/24")
            print("Add 10." + str(address_16_23) + "." + str(address_8_15) + ".30/24 and 10." + str(address_16_23) + "." + str(address_8_15) + ".20/24 to (" + str(current_sat_id) + "," + str(current_orbit_id) + ") to (" + str(right_sat_id) + "," + str(right_orbit_id) + ")")
            isl_idx = isl_idx + 1


def sn_establish_ISLs(remote_machine_ssh, container_id_list, orbit_num, sat_num, constellation_size, isl_idx):
    internal_isl_idx = isl_idx
    sn_establish_inter_ISL_native(remote_machine_ssh, container_id_list, orbit_num, sat_num, constellation_size, internal_isl_idx)
    internal_isl_idx = internal_isl_idx + constellation_size
    sn_establish_intra_ISL_native(remote_machine_ssh, container_id_list, orbit_num, sat_num, constellation_size, internal_isl_idx)


def sn_copy_conf_to_each_container(remote_machine_ssh, container_id_list):
    print("Copy bird configuration file to each container and run routing process.")
    total = len(container_id_list)
    current = 1
    for container_idx in container_id_list:
        sn_remote_cmd(remote_machine_ssh, "docker cp /home/ubuntu/Work/Docker/multi_host_remote_control/bird.conf " + str(container_idx) + ":/bird.conf")
        print("[" + str(current) + "/" + str(total) + "]" + " docker cp bird.conf " + str(container_idx) + ":/bird.conf")
        current = current + 1


def sn_run_bird_by_container_name(remote_machine_ssh, container_id_list):
    print("Start bird in all containers ...")
    idx = 1
    total = len(container_id_list)
    for container_id in container_id_list:
        output_len = 0
        while output_len < 1:
            run_account = sn_remote_cmd(remote_machine_ssh, "docker exec -it " + str(container_id) + " bird -c bird.conf")
            output_len = len(run_account)
        print("[" + str(idx) +"/" + str(total) +"] Bird routing process for container: " + str(container_id) + " has started. ")
        idx = idx + 1

    print("Bird routing in all containers are running.")



def sn_create_inter_machine_connection(remote_machine_ssh, br_conn_name, sat_start, sat_end, phy_conn_name, isl_idx, vtag_idx, conn_prefix, conn_suffix, container_id_list):
    # Create a local ovs bridge connecting to physical interface
    print("Create ISL conn.")
    #print("Execute remote cmd: " + "ovs-vsctl del-br " + str(br_conn_name))
    #print(sn_remote_cmd(remote_machine_ssh, "ovs-vsctl show"))
    sn_remote_cmd(remote_machine_ssh, "ovs-vsctl del-br " + str(br_conn_name))
    print(sn_remote_cmd(remote_machine_ssh, "ovs-vsctl add-br " + str(br_conn_name)))
    print(sn_remote_cmd(remote_machine_ssh, "ovs-vsctl add-port " + str(br_conn_name) + " " + str(phy_conn_name)))

    # For each side satellite, connecting them to the vlan
    for container_idx in range(sat_start - 1, sat_end):
        print("Connecting ovs_container_" + str(container_idx + 1) + " to " + str(br_conn_name))
        #print(sn_remote_cmd(remote_machine_ssh, "ovs-docker del-port " + str(br_conn_name) + " eth5 " + str(container_id_list[container_idx])))
        sn_remote_cmd(remote_machine_ssh, "ovs-docker add-port " + str(br_conn_name) + " eth5 " + str(container_id_list[container_idx]) + " --ipaddress=10." + str(conn_prefix) + "." + str(isl_idx) + "." + str(conn_suffix) + "/24")
        sn_remote_cmd(remote_machine_ssh, "ovs-docker set-vlan " + str(br_conn_name) + " eth5 " + str(container_id_list[container_idx]) + " " + str(vtag_idx))
        vtag_idx = vtag_idx + 1
        isl_idx = isl_idx + 1








