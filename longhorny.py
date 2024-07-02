#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sfc.py

###############################################################################
# Synopsis:                                                                   #
# Longhorny manages SolidFire cluster and volume pairing/unpairing/reporting  #
#                                                                             #
# Author: @scaleoutSean                                                       #
# https://github.com/scaleoutsean/longhorny                                   #
# License: the Apache License Version 2.0                                     #
###############################################################################

# References:
# 1) SolidFire API documentation:
#    https://docs.netapp.com/us-en/element-software/api/
# 2) SolidFire Python SDK:
#    https://solidfire-sdk-python.readthedocs.io/en/latest/index.html
# 3) NetApp Element Software Remote Replication - Feature Description and
#    Deployment Guide (TR-4741):
#    https://www.netapp.com/media/10607-tr4741.pdf

import time
import argparse
import ast
import datetime
import logging
import os
import pprint
from getpass import getpass
from solidfire.factory import ElementFactory
from solidfire import common
from solidfire.common import LOG
from solidfire.common import ApiServerError
from solidfire.common import SdkOperationError
common.setLogLevel(logging.ERROR)


def cluster(args):
    if args.list:
        pairing = report_cluster_pairing(src, dst)
        print("\nCLUSTER (MUTUAL) PAIRING REPORT:\n")
        pprint.pp(pairing)
    elif args.pair:
        pair_cluster(src, dst)
    elif args.unpair:
        unpair_cluster(src, dst)
    else:
        logging.warning(
            "Cluster action not recognized. If this is unhandled, there may be a parsing bug or misconfiguration.")
    return


def report_cluster_pairing(src: dict, dst: dict) -> dict:
    """
    Print to console cluster pairing information between SRC and DST.
    """
    pairing = get_cluster_pairing(src, dst)
    if len(pairing[src['clusterName']]) == 0 and len(
            pairing[dst['clusterName']]) == 0:
        print("Neither cluster has existing cluster pairing relationship(s).")
        logging.warning("Neither " +
                        str(src['clusterName']) +
                        " nor " +
                        str(dst['clusterName']) +
                        " has any cluster pairing relationships.")
    elif len(pairing[src['clusterName']]) == 0 or len(pairing[dst['clusterName']]) == 0:
        logging.warning("One of the clusters is not paired. Number of relationships (SRC/DST): " +
                        str(len(pairing[src['clusterName']])) + "/" + str(len(pairing[dst['clusterName']])) + ".")
    else:
        for site in pairing:
            for i in pairing[site]:
                if i['clusterPairUUID'] in [j['clusterPairUUID']
                                            for j in pairing[site]]:
                    logging.info(
                        "Clusters are paired through clusterPairUUID " + str(i['clusterPairUUID']) + ".")
                else:
                    logging.warning(
                        "Clusters have pairing relationships but are not mutually paired. Foreign relationship: " +
                        str(
                            i['clusterPairUUID']) +
                        ".")
    return (pairing)


def get_cluster_pairing(src: dict, dst: dict) -> dict:
    """
    Return dict with per-site cluster pairings on both clusters.

    May return several or no pairing relationships for each cluster, including with other clusters.
    """
    pairing = {}
    for site in src, dst:
        logging.info("Querying site: " + str(site['mvip']) + ".")
        try:
            r = site['sfe'].list_cluster_pairs().to_json()['clusterPairs']
            logging.info(
                "Result for site: " +
                site['mvip'] +
                " : ",
                str(r) +
                ".")
            pairing[site['clusterName']] = r
        except common.ApiServerError as e:
            logging.error(
                "Error listing cluster pairs for cluster: " + str(site['clusterName']) + ".")
            logging.error("Error: " + str(e))
            exit(100)
    return pairing


def get_exclusive_cluster_pairing(src: dict, dst: dict) -> dict:
    """
    Return dict with 1-to-1 pairing relationships between SRC and DST clusters if and only if that one cluster paring relationship exists.
    """
    pairing = get_cluster_pairing(src, dst)
    if not len(pairing[src['clusterName']]) == 1 and not len(
            pairing[dst['clusterName']]) == 1:
        logging.warning("Number of cluster pair relationships (SRC/DST): " +
                        str(len(pairing[src['clusterName']])) + "/" + str(len(pairing[dst['clusterName']])) + ".")
        return {}
    else:
        for site in pairing:
            for i in pairing[site]:
                if i['clusterPairUUID'] in [j['clusterPairUUID']
                                            for j in pairing[site]]:
                    logging.info(
                        "Clusters are paired through clusterPairUUID " + str(i['clusterPairUUID']) + ".")
                else:
                    logging.warning(
                        "Clusters have pairing relationships but are not mutually paired. Foreign relationship: " +
                        str(
                            i['clusterPairUUID']) +
                        ".")
        return pairing


def pair_cluster(src: dict, dst: dict):
    """
    Pair SRC and DST clusters.

    Works only if each cluster has no existing cluster pairing relationships.
    """
    pairing = get_cluster_pairing(src, dst)
    if pairing[src['clusterName']] == [] and pairing[dst['clusterName']] == []:
        try:
            pairing_key = src['sfe'].start_cluster_pairing().to_json()[
                'clusterPairingKey']
            resp = dst['sfe'].complete_cluster_pairing(pairing_key).to_json()
            if isinstance(resp['clusterPairID'], int):
                logging.info("Pairing is now complete. Cluster " +
                             src['clusterName'] +
                             "returned cluster pair ID " +
                             str(resp['clusterPairID']) +
                             ".")
        except common.ApiServerError as e:
            logging.error("Error: Unable to pair clusters: " + str(e))
            exit(100)
        exclusive_pairing = get_exclusive_cluster_pairing(src, dst)
        print("\nCLUSTER PAIRING STATUS AFTER PAIRING:\n")
        pprint.pp(exclusive_pairing)
        return
    else:
        logging.warning(
            "Clusters are already paired, paired with more than one cluster or in an incomplete pairing state. Use cluster --list to view current status. Exiting.")
        exit(100)


def unpair_cluster(src: dict, dst: dict):
    """
    Unpair clusters identified by SRC and DST.

    Requires that each cluster is not paired or has no more than one cluster pairing relationship.
    """
    pairing = get_exclusive_cluster_pairing(src, dst)
    if pairing == {}:
        logging.error(
            "Clusters are not paired, in an incomplete pairing state or there is some other problem. Use cluster --list to view current status.")
        exit(100)
    cluster_pair_ids = []
    for site in src, dst:
        try:
            resp = site['sfe'].list_cluster_pairs().to_json()['clusterPairs']
            cluster_pair_ids.append(
                (site['clusterName'], resp[0]['clusterPairID']))
        except common.ApiServerError as e:
            logging.error("Error: Unable to list cluster pairs: " + str(e))
            logging.error("Error: " + str(e))
            exit(100)
    volume_relationships_check = list_volume(src, dst, [])
    if len(volume_relationships_check) > 0 or volume_relationships_check != []:
        logging.error(
            "One or both clusters are already have paired volumes. Please unpair all paired volumes first.")
        exit(100)
    if len(resp) == 0 or len(resp) > 1:
        logging.error(
            "Zero or more than one cluster pairs found. Cluster unpairing action requires a 1-to-1 mutual and exclusive relationship. Exiting.")
        exit(100)
    else:
        for site_id_tuple in cluster_pair_ids:
            if site_id_tuple[0] == src['clusterName']:
                site = src
                try:
                    resp = site['sfe'].remove_cluster_pair(
                        site_id_tuple[1]).to_json()
                except common.ApiServerError as e:
                    logging.error(
                        "Error: Unable to unpair clusters: " + str(e))
                    exit(100)
            else:
                site = dst
                try:
                    resp = site['sfe'].remove_cluster_pair(
                        site_id_tuple[1]).to_json()
                except common.ApiServerError as e:
                    logging.error(
                        "Error: Unable to unpair clusters: " + str(e))
                    exit(100)
    exclusive_pairing = get_exclusive_cluster_pairing(src, dst)
    print("\nCLUSTER PAIRING STATUS AFTER UNPAIRING:\n")
    pprint.pp(exclusive_pairing)
    return


def volume(args):
    if args.list:
        try:
            try:
                volume_pair = data_type(args.data)
                logging.info(
                    "Data provided for listing volumes. Querying pair: " +
                    str(volume_pair) +
                    " for pairing status.")
            except BaseException:
                volume_pair = []
            logging.info(
                "Trying to list volumes in list " +
                str(volume_pair) +
                " for pairing status.")
            list_volume(src, dst, volume_pair)
        except Exception as e:
            logging.error("Error: " + str(e))
            exit(200)
    elif args.report:
        try:
            if args.data is None or args.data == '':
                logging.error(
                    "No data provided for volume report customization. Using default value: [].")
                report_data = {}
            else:
                report_data = {}
                pass
            report_volume_replication_status(src, dst, report_data)
        except Exception as e:
            logging.error("Error: " + str(e))
            exit(200)
    elif args.pair:
        pair_data = data_type(args.data)
        pair_volume(src, dst, pair_data)
    elif args.unpair:
        try:
            data = data_type(args.data)
        except BaseException:
            logging.error(
                "Error: Unpair data missing or not understood. Presently only one pair is supported per unpair action, ex: --data '1,2'. Exiting.")
            exit(200)
        if data is None or data == []:
            logging.error(
                "No data found for unpairing. By default, unpair action unpairs nothing rather than everything. Exiting.")
            exit(200)
        unpair_volume(src, dst, data)
    elif args.prime_dst:
        av_data = account_volume_data(args.data)
        prime_destination_volumes(src, dst, av_data)
    elif args.reverse:
        reverse_replication(src, dst)
    elif args.snapshot:
        if args.data is None or args.data == '':
            logging.info(
                "No data input provided. Using default values: 168,long168h-snap.")
            data = '168;long168h-snap'
        else:
            data = args.data
        snap_data = snapshot_data(data)
        snapshot_site(src, dst, snap_data)
    elif args.mismatched:
        list_mismatched_pairs(src, dst)
    elif args.set_mode:
        if args.data is None:
            logging.error(
                "Replication takes two inputs; the mode and one or more volume IDs from the replication source (e.g. --data 'Async;100,101)'. Exiting.")
            exit(200)
        else:
            volume_mode = replication_data(args.data)
            logging.info("Desired replication type: " +
                         str(volume_mode[0]) +
                         " for volume ID(s)" +
                         str(volume_mode[1]) +
                         ".")
            set_volume_replication_mode(src, dst, volume_mode)
    elif args.set_status:
        if args.data is None:
            logging.error(
                "Replication state must be specified. Use --data 'pause' or --data 'resume'. Exiting.")
            exit(200)
        else:
            state = replication_state(args.data)
            if state == 'pause' or state == 'resume':
                logging.info("Desired replication state: " + state)
                set_volume_replication_state(src, dst, state)
    elif args.resize:
        if args.data is None:
            logging.error(
                "Volume resize action requires volume size and volume ID. Use --data '1073741824;100,200' to grow 100 and 200 by 1Gi. Exiting.")
            exit(200)
        else:
            data = increase_volume_size_data(args.data)
            increase_size_of_paired_volumes(src, dst, data)
    elif args.upsize_remote:
        if args.data is None:
            logging.error(
                "Remote volume resize action requires volume IDs of a SRC/DST pair. Use --data '100,200' to grow DST/200 to the size of SRC/100. Exiting.")
            exit(200)
        else:
            data = upsize_remote_volume_data(args.data)
            upsize_remote_volume(src, dst, data)
    else:
        logging.warning("Volume action not recognized.")
    return


def report_volume_replication_status(
        src: dict, dst: dict, report_data: dict) -> dict:
    """
    Print out volume replication report in dictionary format.
    """
    print(
        "TODO: report_volume_replication_status using report_data: " +
        str(report_data))
    return


def snapshot_site(src: dict, dst: dict, snap_data: list) -> dict:
    """
    Create local crash-consistent snapshot for all individual volumes using paired volumes on SRC.

    """
    logging.warning("NOTE: If you have applications that span multiple volumes, you may need to create a dedicated group snapshot for those volumes because you may want to restore those as a group.")
    logging.warning(
        "Taking individual snapshots at SRC using params: " +
        str(snap_data))
    paired_volumes = list_volume(src, dst, [])
    if paired_volumes == []:
        logging.error(
            "No paired volumes found. Ensure volumes are paired before taking a snapshot.")
        exit(200)
    snapshot_retention = str(snap_data[0]) + ':00:00'  # "HH:MM:SS"
    snapshot_name = snap_data[1]
    for v in paired_volumes:
        try:
            r = src['sfe'].create_snapshot(
                v['localVolumeID'], retention=snapshot_retention, name=snapshot_name).to_json()['snapshot']
            snap_meta = "volume ID: " + str(r['volumeID']) + ", snapshot ID: " + str(
                r['snapshotID']) + ", snapshot name: " + str(r['name']) + ", expiration time" + str(r['expirationTime'])
            logging.info("Snapshot created for volume ID " +
                         str(v['localVolumeID']) + ": " + snap_meta)
        except common.ApiServerError as e:
            logging.error(
                "Error creating snapshot for volume ID " +
                str(v['localVolumeID']) +
                ".")
            logging.error("Error: " + str(e))
            exit(200)
    return


def upsize_remote_volume(src: dict, dst: dict, data: list):
    """
    Increase size of DST volume to match the size of SRC volume.

    The main use case for upsizing just the remote paired volume is Trident CSI generally increases only the size of the source volume, leaving the remote volume smaller.
    This function allows the destination volume to be increased to match the source volume and replication to continue.
    As the volumes are mismatched to begin with, the function does not check multiple volume pairing details - it simply increases the size of the paired destination volume to match the source volume.
    """
    logging.info("Attempting to grow paired DST volume ID " +
                 str(data[1]) + " to size of SRC volume ID " + str(data[0]) + ".")
    src_vol_params = {
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False,
        'volumeIDs': [
            data[0]]}
    dst_vol_params = {
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False,
        'volumeIDs': [
            data[1]]}
    src_vol = src['sfe'].invoke_sfapi(
        method='ListVolumes',
        parameters=src_vol_params)
    dst_vol = dst['sfe'].invoke_sfapi(
        method='ListVolumes',
        parameters=dst_vol_params)
    if src_vol['volumes'] == [] or dst_vol['volumes'] == []:
        logging.error("Volume ID " +
                      str(data[0]) +
                      " and/or " +
                      str(data[1]) +
                      " not found on SRC or DST cluster, respectively. Exiting.")
        exit(200)
    else:
        logging.info("Volumes found: SRC volume ID " +
                     str(data[0]) + " and DST volume ID " + str(data[1]) + ".")
    src_vol_mode = src_vol['volumes'][0]['access']
    dst_vol_mode = dst_vol['volumes'][0]['access']
    src_vol_total_size = src_vol['volumes'][0]['totalSize']
    dst_vol_total_size = dst_vol['volumes'][0]['totalSize']
    if not dst_vol_total_size < src_vol_total_size:
        logging.error("SRC volume ID " +
                      str(data[0]) +
                      " must be larger than DST volume ID " +
                      str(data[1][1]) +
                      " for this action to work. Exiting.")
        exit(200)
    try:
        pause_params = {'volumeID': data[0], 'pausedManual': True}
        src['sfe'].invoke_sfapi(
            method='ModifyVolumePair',
            parameters=pause_params)
        logging.info("Paused replication for SRC volume ID " +
                     str(data[0]) + ".")
    except BaseException:
        logging.error(
            "Error pausing replication for SRC volume ID " + str(data[0]) + ".")
        exit(200)
    try:
        r = dst['sfe'].modify_volume(data[1], total_size=src_vol_total_size)
        logging.info("Increased size of DST volume ID " +
                     str(data[1]) + " to " + str(src_vol_total_size) + " bytes.")
    except Exception as e:
        logging.error(
            "Error increasing size of DST volume ID " +
            str(
                data[1]) +
            " to " +
            str(src_vol_total_size) +
            " bytes. Please manually resize the DST volume. You may use volume --mismatched to view. Exiting.\n" +
            str(e))
        exit(200)
    resume_params = {'volumeID': data[0], 'pausedManual': False}
    try:
        logging.info(
            "Will resume replication for the pair if SRC is readWrite and DST replicationTarget.")
        if src_vol_mode == 'readWrite' and dst_vol_mode == 'replicationTarget':
            r = src['sfe'].invoke_sfapi(
                method='ModifyVolumePair',
                parameters=resume_params)
            logging.info(
                "Resumed replication for volume pair on SRC volume ID " + str(data[0]) + ".")
        else:
            logging.warning("Volume ID " +
                            str(data[0]) +
                            " is in mode " +
                            str(src_vol_mode) +
                            " and paired with volume ID " +
                            str(data[1]) +
                            " in mode " +
                            str(dst_vol_mode) +
                            ". Skipping attempt to resume replication.")
    except BaseException:
        logging.error(
            "Error resuming replication for volume ID " +
            str(
                data[0]) +
            ". The volumes should be resized but replication is still paused. Try manually resuming. Exiting.")
        exit(200)
    try:
        src_vol_final = src['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=src_vol_params)
        dst_vol_final = dst['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=dst_vol_params)
    except Exception as e:
        logging.error(
            "Error listing volumes after DST volume resizing. Exiting.\n" +
            str(e))
        exit(200)
    src_vol_details = {
        'volumeID': src_vol_final['volumes'][0]['volumeID'],
        'name': src_vol_final['volumes'][0]['name'],
        'totalSize': src_vol_final['volumes'][0]['totalSize'],
        'access': src_vol_final['volumes'][0]['access'],
        'state': src_vol_final['volumes'][0]['volumePairs'][0]['remoteReplication']['state'],
        'volumePairs': src_vol_final['volumes'][0]['volumePairs'][0]['remoteVolumeID']
    }
    dst_vol_details = {
        'volumeID': dst_vol_final['volumes'][0]['volumeID'],
        'name': dst_vol_final['volumes'][0]['name'],
        'totalSize': dst_vol_final['volumes'][0]['totalSize'],
        'access': dst_vol_final['volumes'][0]['access'],
        'volumePairs': dst_vol_final['volumes'][0]['volumePairs'][0]['remoteVolumeID']
    }
    if src_vol_details['totalSize'] == dst_vol_details['totalSize']:
        logging.info("Volume ID " +
                     str(data[0]) +
                     " and " +
                     str(data[1]) +
                     " have been successfully resized to " +
                     str(src_vol_details['totalSize']) +
                     " bytes. (" +
                     str(round(src_vol_details['totalSize'] /
                               (1024 *
                                1024 *
                                1024), 2)) +
                     " GiB).")
    else:
        logging.error("Volume ID " +
                      str(data[0]) +
                      " and " +
                      str(data[1]) +
                      " have not been resized to " +
                      str(src_vol_details['totalSize']) +
                      " bytes. Use volumes --mismatch to find what happened. Exiting.")
        exit(200)
    resize_action_report = [src_vol_details, dst_vol_details]
    print("\nUPSIZE REMOTE VOLUME ACTION REPORT:\n")
    pprint.pp(resize_action_report)
    return


def increase_size_of_paired_volumes(src: dict, dst: dict, data: list):
    """
    Increase size of paired volumes on SRC and DST clusters by the byte amount specified in the data field.

    volume --grow --data='1073741824;100,200' means grow 100 and 200 by 1Gi.
    This function first uses ListVolumes to confirm the source (volume ID) exists in readWrite access mode and is paired with a volume on the destination cluster.
    """
    logging.info("Attempting to grow paired volumes SRC volume ID " +
                 str(data[1][0]) +
                 " and DST volume ID " +
                 str(data[1][1]) +
                 " by " +
                 str(data[0]) +
                 " bytes.")
    src_vol_params = {
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False,
        'volumeIDs': [
            data[1][0]]}
    dst_vol_params = {
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False,
        'volumeIDs': [
            data[1][1]]}
    src_vol = src['sfe'].invoke_sfapi(
        method='ListVolumes',
        parameters=src_vol_params)
    dst_vol = dst['sfe'].invoke_sfapi(
        method='ListVolumes',
        parameters=dst_vol_params)
    if src_vol['volumes'] == [] or dst_vol['volumes'] == []:
        logging.error("Volume ID " +
                      str(data[1][0]) +
                      " and/or " +
                      str(data[1][1]) +
                      " not found on SRC or DST cluster, respectively. Exiting.")
        exit(200)
    else:
        logging.info("Volumes found: SRC volume ID " +
                     str(data[1][0]) +
                     " and DST volume ID " +
                     str(data[1][1]) +
                     ".")
    src_vol_mode = src_vol['volumes'][0]['access']
    dst_vol_mode = dst_vol['volumes'][0]['access']
    src_vol_total_size = src_vol['volumes'][0]['totalSize']
    dst_vol_total_size = dst_vol['volumes'][0]['totalSize']
    if src_vol_total_size != dst_vol_total_size:
        logging.warning("SRC volume ID " +
                        str(data[1][0]) +
                        " and DST volume ID " +
                        str(data[1][1]) +
                        " are not the same size. Exiting.")
        exit(200)
    if data[0] > (src_vol_total_size * 2):
        logging.error("SRC volume ID " +
                      str(data[0]) +
                      " would be increased by " +
                      str(data[0]) +
                      " bytes, which is more than twice its current size of " +
                      str(src_vol_total_size) +
                      " bytes. To avoid mistakes, this function cannot increase volume size by either more than 2x or 1 TiB at a time. Exiting.")
        exit(200)
    new_total_size = data[0] + src_vol_total_size
    if new_total_size > 17592186044416:
        logging.error("Volumes SRC/" +
                      str(data[1][0]) +
                      ", and DST/" +
                      str(data[1][1]) +
                      " would be increased to " +
                      str(new_total_size) +
                      " bytes, which is more than the SolidFire maximum volume size of 16 TiB. Exiting.")
        exit(200)
    # NOTE: we user src volume's pairing configuration and status to determine
    # if replication is paused or not
    dst_vol_replication_state = src_vol['volumes'][0]['volumePairs'][0]['remoteReplication']['state']
    dst_vol_id = src_vol['volumes'][0]['volumePairs'][0]['remoteVolumeID']
    if src_vol_mode != 'readWrite' or dst_vol_id != data[1][1] or dst_vol_mode != 'replicationTarget':
        logging.error("Volume ID " +
                      str(data[1][0]) +
                      " is in mode " +
                      str(src_vol_mode) +
                      " and paired with volume ID " +
                      str(dst_vol_id) +
                      " with replication state " +
                      str(dst_vol_replication_state) +
                      ".")
        exit(200)
    else:
        logging.info("Volume ID " +
                     str(data[1][0]) +
                     " is in " +
                     str(src_vol_mode) +
                     " mode, paired with " +
                     str(dst_vol_id) +
                     " in replication state " +
                     str(dst_vol_replication_state) +
                     ". Continuing.")
    try:
        pause_params = {'volumeID': data[1][0], 'pausedManual': True}
        src['sfe'].invoke_sfapi(
            method='ModifyVolumePair',
            parameters=pause_params)
        logging.info("Paused replication for SRC volume ID " +
                     str(data[1][0]) + ".")
    except BaseException:
        logging.error(
            "Error pausing replication for SRC volume ID " + str(data[1][0]) + ".")
        exit(200)
    try:
        r = dst['sfe'].modify_volume(data[1][1], total_size=new_total_size)
        logging.info("Increased size of DST volume ID " +
                     str(data[1][0]) + " to " + str(data[0]) + " bytes.")
    except Exception as e:
        logging.error("Error increasing size of DST volume ID " +
                      str(data[1][1]) +
                      " to " +
                      str(data[0]) +
                      " bytes. Please manually resize the DST volume. You may use volume --mismatched to view. Exiting.\n" +
                      str(e))
        exit(200)
    try:
        logging.info("Size of the destination volume has been increased.")
        r = src['sfe'].modify_volume(data[1][0], total_size=new_total_size)
        logging.info("Increased size of SRC volume ID " +
                     str(data[1][0]) + " to " + str(new_total_size) + " bytes.")
    except Exception as e:
        logging.error(
            "Error increasing size of volume " +
            str(
                data[1][0]) +
            " to " +
            str(new_total_size) +
            " bytes. Please manually resize the SRC volume and set replication to resume. You may use volume --mismatched to view. Exiting.\n" +
            str(e))
        exit(200)
    resume_params = {'volumeID': data[1][0], 'pausedManual': True}
    try:
        logging.info("Resuming replication for volume pair.")
        r = src['sfe'].invoke_sfapi(
            method='ModifyVolumePair',
            parameters=resume_params)
        logging.info(
            "Resumed replication for volume pair on SRC volume ID " + str(data[1][0]) + ".")
    except BaseException:
        logging.error(
            "Error resuming replication for volume ID " +
            str(
                data[1][0]) +
            ". The volumes should be resized but replication is still paused. Try manually resuming. Exiting.")
        exit(200)
    try:
        src_vol_final = src['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=src_vol_params)
        dst_vol_final = dst['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=dst_vol_params)
    except Exception as e:
        logging.error(
            "Error listing volumes after resizing. Exiting.\n" +
            str(e))
        exit(200)
    src_vol_details = {
        'volumeID': src_vol_final['volumes'][0]['volumeID'],
        'name': src_vol_final['volumes'][0]['name'],
        'totalSize': src_vol_final['volumes'][0]['totalSize'],
        'access': src_vol_final['volumes'][0]['access'],
        'state': src_vol_final['volumes'][0]['volumePairs'][0]['remoteReplication']['state'],
        'volumePairs': src_vol_final['volumes'][0]['volumePairs'][0]['remoteVolumeID']
    }
    dst_vol_details = {
        'volumeID': dst_vol_final['volumes'][0]['volumeID'],
        'name': dst_vol_final['volumes'][0]['name'],
        'totalSize': dst_vol_final['volumes'][0]['totalSize'],
        'access': dst_vol_final['volumes'][0]['access'],
        'volumePairs': dst_vol_final['volumes'][0]['volumePairs'][0]['remoteVolumeID']
    }
    if src_vol_details['totalSize'] == dst_vol_details['totalSize']:
        logging.info("Volume ID " +
                     str(data[1][0]) +
                     " and " +
                     str(data[1][1]) +
                     " have been successfully resized to " +
                     str(src_vol_details['totalSize']) +
                     " bytes. (" +
                     str(round(src_vol_details['totalSize'] /
                               (1024 *
                                1024 *
                                1024), 2)) +
                     " GiB).")
    else:
        logging.error("Volume ID " +
                      str(data[1][0]) +
                      " and " +
                      str(data[1][1]) +
                      " have not been resized to " +
                      str(src_vol_details['totalSize']) +
                      " bytes. Use volumes --mismatch to find what happened. Exiting.")
        exit(200)
    resize_action_report = [src_vol_details, dst_vol_details]
    print("\nRESIZE ACTION REPORT:\n")
    pprint.pp(resize_action_report)
    return


def list_mismatched_pairs(src: dict, dst: dict) -> dict:
    """
    List mismatched volume pairs.

    Mismatched pairs are those for which there's a unilateral pairing, volume sizes do not match or something else appears wrong.
    """
    params = {'isPaired': True}
    existing_pairs = {}
    src_pairs = src['sfe'].invoke_sfapi(
        method='ListVolumes',
        parameters=params)['volumes']
    dst_pairs = dst['sfe'].invoke_sfapi(
        method='ListVolumes',
        parameters=params)['volumes']
    src_ids = [(i['volumeID'], i['volumePairs'][0]['remoteVolumeID'])
               for i in src_pairs]
    dst_ids = [(i['volumeID'], i['volumePairs'][0]['remoteVolumeID'])
               for i in dst_pairs]
    if len(src_ids) != len(dst_ids):
        logging.warning("SRC and DST have different number of volume pairings at SRC/DST: " +
                        str(len(src_ids)) + "/" + str(len(dst_ids)) + ".")
    src_account_ids = [(i['volumeID'], i['accountID']) for i in src_pairs]
    dst_account_ids = [(i['volumeID'], i['accountID']) for i in dst_pairs]
    if len(set([i[1] for i in src_account_ids])) > 1:
        logging.warning("Multiple account IDs found on paired volumes at SRC: " +
                        str(len(set([i[1] for i in src_account_ids]))) + ".")
    if len(set([i[1] for i in dst_account_ids])) > 1:
        logging.warning("Multiple account IDs found on paired volumes at DST: " +
                        str(len(set([i[1] for i in dst_account_ids]))) + ".")
    mismatch = []
    for p in src_ids:
        pr = (p[1], p[0])
        if pr not in dst_ids:
            logging.warning("Volume ID " +
                            str(p[0]) +
                            " is paired on SRC but not on DST cluster.")
    for p in dst_ids:
        pr = (p[1], p[0])
        if pr not in src_ids:
            logging.warning("Volume ID " +
                            str(p[0]) +
                            " is paired on DST but not on SRC cluster.")
    if len(src_ids) == 0 and len(dst_ids) == 0:
        logging.warning("No volumes found on one or both sides.")
        return
    elif len(src_ids) == 0 or len(dst_ids) == 0:
        logging.warning(
            "One or both sides have no paired volumes. Number of paired volumes at SRC/DST:" +
            len(src_ids) +
            "/" +
            len(dst_ids) +
            ".")
        return
    else:
        site_pairs = {}
        s_list = []
        for pair in src_pairs:
            kvs = {
                'accountID': pair['accountID'],
                'volumeID': pair['volumeID'],
                'name': pair['name'],
                'deleteTime': pair['deleteTime'],
                'purgeTime': pair['purgeTime'],
                'totalSize': pair['totalSize'],
                'enable512e': pair['enable512e'],
                'volumePairUUID': pair['volumePairs'][0]['volumePairUUID'],
                'remoteVolumeID': pair['volumePairs'][0]['remoteVolumeID'],
                'remoteVolumeName': pair['volumePairs'][0]['remoteVolumeName']
            }
            if 'qos' in pair.keys():
                qos = pair['qos']
                pair['qos'] = qos
            else:
                qos_policy_id = pair['qosPolicyID']
                pair['qosPolicyID'] = qos_policy_id
            s_list.append(kvs)
        site_pairs[src['clusterName']] = s_list
        d_list = []
        for pair in dst_pairs:
            kvs = {
                'accountID': pair['accountID'],
                'volumeID': pair['volumeID'],
                'name': pair['name'],
                'deleteTime': pair['deleteTime'],
                'purgeTime': pair['purgeTime'],
                'totalSize': pair['totalSize'],
                'enable512e': pair['enable512e'],
                'volumePairUUID': pair['volumePairs'][0]['volumePairUUID'],
                'remoteVolumeID': pair['volumePairs'][0]['remoteVolumeID'],
                'remoteVolumeName': pair['volumePairs'][0]['remoteVolumeName']
            }
            if 'qos' in pair.keys():
                pair['qos'] = qos
            else:
                qos_policy_id = pair['qosPolicyID']
                pair['qosPolicyID'] = qos_policy_id
            d_list.append(kvs)
        site_pairs[dst['clusterName']] = d_list
        unique = []
        for i in site_pairs[src['clusterName']]:
            mismatch = {}
            if i['volumePairUUID'] not in (
                    j['volumePairUUID'] for j in site_pairs[dst['clusterName']]):
                mismatch[src['clusterName']] = {
                    'volumeID': i['volumeID'],
                    'volumePairUUID': i['volumePairUUID'],
                    'volumePairUUID': i['volumePairUUID'],
                    'mismatchSite': dst['clusterName'],
                    'remoteVolumeID': i['remoteVolumeID']}
                logging.warning("Mismatch found at SRC: vol ID " +
                                str(i['volumeID']) +
                                " in relationship " +
                                str(i['volumePairUUID']) +
                                " found at SRC, but relationship from paired SRC volume ID is missing: " +
                                str(i['remoteVolumeID']) +
                                ".")
                unique.append(mismatch)
            else:
                pass
        for i in site_pairs[dst['clusterName']]:
            mismatch = {}
            if i['volumePairUUID'] not in (
                    j['volumePairUUID'] for j in site_pairs[src['clusterName']]):
                mismatch[dst['clusterName']] = {
                    'volumeID': i['volumeID'],
                    'volumePairUUID': i['volumePairUUID'],
                    'remoteSite': src['clusterName'],
                    'remoteVolumeID': i['remoteVolumeID']}
                logging.warning("Mismatch found at DST: vol ID " +
                                str(i['volumeID']) +
                                " in relationship " +
                                str(i['volumePairUUID']) +
                                " found at SRC, but relationship from paired SRC volume ID is missing: " +
                                str(i['remoteVolumeID']) +
                                ".")
                unique.append(mismatch)
            else:
                pass
        print("\nMISMATCHED PAIRED VOLUMES ONLY:\n")
        pprint.pp(unique)
    return


def prime_destination_volumes(src, dst, data):
    """
    Creates volumes on DST cluster for specified account, with volume properties based on list of Volume IDs from SRC but set to replicationTarget mode.

    Takes a two inputs, the first of which is a pair of SRC and DST account IDs and the second is a list of volume IDs (VOL1, VOL2) to use as templates at the remote site.
    """
    try:
        try:
            src_account_vols = src['sfe'].list_volumes_for_account(data[0][0]).to_json()[
                'volumes']
        except BaseException:
            logging.error(
                "Error getting account volumes for source site account ID: " +
                str(
                    data[0][0]) +
                ". Make sure the account ID exists. Exiting.")
            exit(200)
        # list of SRC Volume IDs to be used as templates
        src_vid = [i for i in data[1]]
        for v in src_account_vols:
            if v['volumeID'] in src_vid:
                logging.info("Volume ID " + str(v['volumeID']) + " found to belong to account ID " + str(
                    data[0][0]) + ". Checking the volume for existing replication relationships (must be none).")
                if 'volumePairs' in v.keys() and v['volumePairs'] != []:
                    logging.error("Error: Volume ID " +
                                  str(v['volumeID']) +
                                  " has replication relationships. Volumes used for priming must not be already paired. Exiting.")
                    exit(200)
    except BaseException:
        logging.error(
            "Error getting account volumes for account ID: " +
            str(
                data[0][0]) +
            ". All of the SRC volume IDs must be owned by the specific SRC account ID. Exiting.")
        exit(200)
    src_volumes = []
    for v in src_account_vols:
        if v['volumeID'] in src_vid:  # skip volumes not in the DATA list of volume IDs
            if 'qos' in v.keys():
                src_volume = {
                    'volumeID': v['volumeID'],
                    'enable512e': v['enable512e'],
                    'fifoSize': v['fifoSize'],
                    'minFifoSize': v['minFifoSize'],
                    'name': v['name'],
                    'qos': v['qos'],
                    'totalSize': v['totalSize']}
            else:
                src_volume = {
                    'volumeID': v['volumeID'],
                    'enable512e': v['enable512e'],
                    'fifoSize': v['fifoSize'],
                    'minFifoSize': v['minFifoSize'],
                    'name': v['name'],
                    'qosPolicyID': v['qosPolicyID'],
                    'totalSize': v['totalSize']}
            src_volumes.append(src_volume)
    logging.warning(
        "SRC volumes to be used as template for volume creation on DST cluster:")
    pprint.pp(src_volumes)
    try:
        dst_account_id = dst['sfe'].get_account_by_id(data[0][1]).to_json()[
            'account']['accountID']
        if dst_account_id == data[0][1]:
            print("DST account exists (DATA vs API response): " +
                  str(data[0][1]) + "," + str(dst_account_id) + ".")
            logging.info("DST account exists (DATA vs API response): " +
                         str(data[0][1]) + "," + str(dst_account_id) + ".")
    except BaseException:
        logging.error("DST account ID " +
                      str(data[0][1]) +
                      " does not exist or cannot be queried. Exiting.")
        exit(200)
    dst_volumes = []
    for v in src_volumes:
        if 'qos' in v.keys():
            params = {
                'accountID': dst_account_id,
                'name': v['name'],
                'totalSize': v['totalSize'],
                'enable512e': v['enable512e'],
                'qos': v['qos'],
                'fifoSize': v['fifoSize'],
                'minFifoSize': v['minFifoSize']}
        else:
            print(
                "QoS not found in volume properties. Using qosPolicyID instead:",
                v['qosPolicyID'])
            params = {
                'accountID': dst_account_id,
                'name': v['name'],
                'totalSize': v['totalSize'],
                'enable512e': v['enable512e'],
                'qosPolicyID': v['qos'],
                'fifoSize': v['fifoSize'],
                'minFifoSize': v['minFifoSize']}
        try:
            logging.info(
                "Creating volume on DST cluster using params: " +
                str(params) +
                ".")
            dst_volume = dst['sfe'].invoke_sfapi(
                method='CreateVolume', parameters=params)
            dst_volumes.append(
                (v['volumeID'], dst_volume['volume']['volumeID']))
        except ApiServerError as e:
            logging.error("Error creating volume on DST cluster: " + str(e))
            exit(200)
    try:
        if len(dst_volumes) < 500:
            logging.info(
                "Less than 500 volumes to be modified. Using the bulk volume modification API.")
            r = dst['sfe'].modify_volumes(
                [i[1] for i in dst_volumes], access='replicationTarget')
        else:
            logging.info(
                "More than 500 volumes to be modified. Using the individual volume modification API. Inspect DST for correctness before pairing.")
            for i in dst_volumes:
                try:
                    r = dst['sfe'].modify_volume(
                        i[1], access='replicationTarget')
                    logging.info("Modified volume ID " +
                                 str(i[1]) +
                                 " to access mode replicationTarget.")
                except ApiServerError as e:
                    logging.error(
                        "Error modifying volume ID " +
                        str(
                            i[1]) +
                        " to access mode replicationTarget. Exiting loop to prevent massive mismatches in access mode of new volumes at DST.")
                    logging.error("Error: " + str(e))
                    exit(200)
    except ApiServerError as e:
        print("API server response code: ", e)
        logging.warning(
            "setting DST volumes to access mode: replicationTarget. Please review and remediate. API server message: ",
            str(e))
    if dst_volumes != []:
        print("DST volumes created [(SRC,DST)..]: " +
              str([i[1] for i in dst_volumes]))
        dst_volumes_str = ";".join(
            [str(i[0]) + "," + str(i[1]) for i in dst_volumes])
        print(
            "New DST volumes ought to be in access mode replicationTarget. Inspect new DST volumes for correctness and then you may pair the volumes with data argument: --data " +
            "\"" +
            dst_volumes_str +
            "\".")
        pprint.pp(dst_volumes)
    return


def list_volume(src: dict, dst: dict, volume_pair: list) -> dict:
    """
    List mutually paired volumes on SRC and DST cluster.

    If volume pair list is not provided, list all mutually paired volumes.
    If volume pair list is provided, list only those volume pairs if such pair(s) exist in a paired relationship.
    Volumes paired asymmetrically (one-sided, or different volume sizes) are not listed as they're considered mismatched (see volume --mismatch).
    """
    pairing = get_exclusive_cluster_pairing(src, dst)
    if pairing == {}:
        logging.error(
            "Clusters are already paired with more than one cluster or in an incomplete pairing state. Use cluster --list to view current status.")
        exit(200)
    paired_volumes = []
    if volume_pair == []:
        logging.info(
            "No volume pair data provided. Listing all paired active volumes.")
        params = {
            'isPaired': True,
            'volumeStatus': 'active',
            'includeVirtualVolumes': False}
        volume = src['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=params)['volumes']
    elif isinstance(volume_pair, list):
        volume_ids = []
        for i in volume_pair:
            if not isinstance(i, tuple):
                logging.error("Volume pair data not understood. Exiting.")
                exit(200)
            else:
                volume_ids.append(int(i[0]))
        params = {
            'volumeIDs': volume_ids,
            'isPaired': True,
            'volumeStatus': 'active',
            'includeVirtualVolumes': False}
        volume = src['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=params)['volumes']
    else:
        logging.error("Volume pair data not understood. Exiting.")
        exit(200)
    for v in volume:
        if 'volumePairs' in v.keys() and v['volumePairs'] != []:
            if v['volumePairs'] is not None and not len(v['volumePairs']) > 1:
                for rr in v['volumePairs']:
                    if rr['clusterPairID'] != pairing[src['clusterName']
                                                      ][0]['clusterPairID']:
                        print("Suspicious volume:", str(v['volumeID']) +
                              " Name: " +
                              v['name'], "with pairing *cluster* relationship ID", rr['clusterPairID'], "does not match the cluster pair ID " +
                              str(pairing[src['clusterName']][0]['clusterPairID']) +
                              ". Ensure the volume is not paired. Exiting.")
                        logging.error("Found volume paired with with a cluster other than DST. Exiting. Use cluster --list or volume --list to verify one-to-one cluster peering relationship. Unknown clusterPairID " + str(
                            rr['clusterPairID']) + " found for volume ID/name:" + str(v['volumeID']) + ", " + v['name'] + ".")
                        exit(200)
                    else:
                        logging.info("Confirmed that volume" +
                                     str(v['volumeID']) +
                                     " is paired with clusterPairID " +
                                     str(pairing[src['clusterName']][0]['clusterPairID']) +
                                     ".")
                        paired_info = {
                            'clusterPairID': rr['clusterPairID'],
                            'localVolumeID': v['volumeID'],
                            'localVolumeName': v['name'],
                            'remoteVolumeName': rr['remoteVolumeName'],
                            'remoteReplicationMode': rr['remoteReplication']['mode'],
                            'remoteReplicationPauseLimit': rr['remoteReplication']['pauseLimit'],
                            'remoteReplicationStateSnapshots': rr['remoteReplication']['snapshotReplication']['state'],
                            'remoteReplicationState': rr['remoteReplication']['snapshotReplication']['state'],
                            'remoteVolumeID': rr['remoteVolumeID'],
                            'volumePairUUID': rr['volumePairUUID']
                        }
                        logging.info("Paired volume found for SRC volume ID " +
                                     str(v['volumeID']) +
                                     ", name " +
                                     str(v['volumeID']) +
                                     " - remote volume " +
                                     str(rr['remoteVolumeID']) +
                                     ", name " +
                                     str(rr['remoteVolumeName']) +
                                     ".")
                        paired_volumes.append(paired_info)
            else:
                print(
                    "Suspicious volume:", str(
                        v['volumeID']) + " Name: " + v['name'])
                logging.warning(
                    "Volume is paired with more than one volume. Use cluster --list to verify one-to-one cluster peering relationship. Volume ID and name:" +
                    str(
                        v['volumeID']) +
                    "," +
                    v['name'])
        else:
            logging.info("No paired volumes found for volume" + v['name'])
    if volume_pair == []:
        print("\nPAIRED VOLUMES REPORT:\n")
        pprint.pp(paired_volumes)
    elif isinstance(volume_pair, list):
        print(
            "\nVOLUMES REPORT FOR SPECIFIED VOLUME PAIR(S): " +
            str(volume_pair) +
            "\n")
        pprint.pp(paired_volumes)
    else:
        logging.error("Volume pair data not understood. Exiting.")
        exit(200)
    return paired_volumes


def pair_volume(src: dict, dst: dict, data: tuple) -> dict:
    """
    Pair volume pairs on SRC and DST clusters.

    A pairing action may result in (eventual or immediate) warning, which may be benign or require action for replication to work.
    pair_volume only pairs and does not remedy possible warnings or fix network and firewall issues preventing replication.
    https://docs.netapp.com/us-en/element-software/storage/reference_replication_volume_pairing_warnings.html
    """
    pairing = get_cluster_pairing(src, dst)
    if not pairing[src['clusterName']
                   ][0]['clusterPairID'] == pairing[src['clusterName']][0]['clusterPairID']:
        logging.error("Clusters pair IDs do not match. SRC/DST:" +
                      str(pairing[src['clusterName']][0]['clusterPairID']) +
                      "," +
                      str(pairing[dst['clusterName']][0]['clusterPairID']) +
                      ". Exiting.")
        exit(200)
    paired_volumes = list_volume(src, dst, [])
    src_volume_ids = [item['localVolumeID'] for item in paired_volumes]
    if len(src_volume_ids) != 0:
        s_params = {
            'volumeIDs': src_volume_ids,
            'isPaired': True,
            'volumeStatus': 'active',
            'includeVirtualVolumes': False}
        try:
            src_vol = src['sfe'].invoke_sfapi(
                method='ListVolumes', parameters=s_params)['volumes']
        except BaseException:
            logging.error(
                "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
            exit(200)
        src_vol_mode = [v['access'] for v in src_vol]
        if list(set(src_vol_mode)) != ['readWrite']:
            logging.error("SRC volume access mode is not suitable for pairing. SRC site volumes are in mode: " +
                          str(src_vol_mode[0]) +
                          ". Direction of replication must be from readWrite to replicationTarget. Swap SRC/DST and change volume ID order (SRC first). Exiting.")

    for v_pair in data:
        s_params = {
            'volumeIDs': [
                v_pair[0]],
            'isPaired': False,
            'volumeStatus': 'active',
            'includeVirtualVolumes': False}
        d_params = {
            'volumeIDs': [
                v_pair[1]],
            'isPaired': False,
            'volumeStatus': 'active',
            'includeVirtualVolumes': False}
        try:
            src_vol = src['sfe'].invoke_sfapi(
                method='ListVolumes', parameters=s_params)
            dst_vol = dst['sfe'].invoke_sfapi(
                method='ListVolumes', parameters=d_params)
            if src_vol['volumes'] == [] or dst_vol['volumes'] == []:
                logging.error(
                    "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
                exit(200)
        except common.ApiServerError as e:
            logging.error(
                "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
            logging.error("Error: " + str(e))
            exit(200)
        prop_keys = ['blockSize', 'enable512e', 'status', 'totalSize']
        if src_vol['volumes'][0]['access'] == 'readWrite' and dst_vol['volumes'][0]['access'] == 'replicationTarget':
            logging.info(
                "Volume access mode suitable for SRC and DST volumes:",
                src_vol['volumes'][0]['access'],
                dst_vol['volumes'][0]['status'])
            for k in prop_keys:
                if src_vol['volumes'][0][k] == dst_vol['volumes'][0][k]:
                    logging.info("Volume property match for key: " +
                                 k +
                                 " SRC: " +
                                 str(src_vol['volumes'][0][k]) +
                                 " DST: " +
                                 str(dst_vol['volumes'][0][k]) +
                                 ".")
                else:
                    logging.error("Volume property mismatch for key: " +
                                  str(k) +
                                  ". SRC: " +
                                  str(src_vol['volumes'][0][k]) +
                                  " DST: " +
                                  str(dst_vol['volumes'][0][k]) +
                                  ". Ensure consistency of settings before pairing. Exiting.")
                    if k == 'totalSize':
                        logging.error(
                            "Volume size mismatch. Enlarge the smaller volume or create a new pair with identical sizes and try again.")
                    if k == 'enable512e':
                        logging.error(
                            "One of the volumes has to be recreated so that both have the same enable512e setting.")
                    exit(200)
        else:
            logging.error(
                "Volume access mode not suitable (SRC/DST): " +
                src_vol['volumes'][0]['access'] +
                " and " +
                dst_vol['volumes'][0]['access'] +
                ". Verify direction of cluster replication and set the DST volume ID to reaplicationTarget. Exiting.")
            exit(200)
    for v_pair in data:
        try:
            src_key = src['sfe'].start_volume_pairing(v_pair[0])
            params = {
                'volumeID': v_pair[1],
                'volumePairingKey': src_key.volume_pairing_key}
            dst['sfe'].invoke_sfapi(
                method='CompleteVolumePairing',
                parameters=params)
            logging.warning("Pairing has been successful. SRC volume ID " +
                            str(v_pair[0]) +
                            " has been paired with DST volume ID " +
                            str(v_pair[1]) +
                            ".")
        except common.ApiServerError as e:
            logging.error(
                "Error pairing volumes. SolidFire API returned an error. ")
            logging.error("Error: " + str(e))
            exit(200)
    return


def unpair_volume(src: dict, dst: dict, data: tuple) -> dict:
    """
    Unpair pair of volumes on SRC and DST cluster.

    Pairing relationship must exist on both sides. If the pair is not symmetric, exit with error.
    """
    paired_volumes = list_volume(src, dst, data)
    pvt = [((item['localVolumeID'], item['remoteVolumeID']))
           for item in paired_volumes]
    if len(data) == 1 and data[0] in pvt:
        delete_pair = dict(zip(['local', 'remote'], data[0]))
        if args.dry == True or args.dry == 'True' or args.dry == 'true' or args.dry == 'on' or args.dry == 'On' or args.dry == 'ON':
            logging.info(
                "Dry run in unpair action is ON. Value: " + str(args.dry))
            print(
                "\n===> Dry run: replication relationship for volume IDs that would be removed (SRC, DST):",
                data)
        else:
            logging.warning(
                "Dry run in unpair action is OFF. Value: " + str(args.dry))
            try:
                src['sfe'].remove_volume_pair(delete_pair['local'])
                dst['sfe'].remove_volume_pair(delete_pair['remote'])
                logging.warning(
                    "Volume IDs unpaired at SRC/DST: " +
                    str(delete_pair))
            except common.ApiServerError as e:
                logging.error("Error unpairing volumes. Exiting.")
                logging.error("Error: " + str(e))
                exit(200)
        return
    elif len(data) > 1 and data[0] in pvt:
        logging.error(
            "More than one volume pair found. That could be risky and is currently not supported. Multiple pairs should be deleted one by one. Exiting.")
        exit(200)
    elif len(data) == 1 or data[0] not in pvt:
        logging.error(
            "Volume pair not found in list of volume replication pairs. Use --list to verify, including SRC and DST settings. Exiting.")
        exit(200)
    else:
        logging.error(
            "Volume pair not found in list of volume replication pairs. Use --list to verify, including SRC and DST settings. Exiting.")
        exit(200)


def set_volume_replication_mode(src: dict, dst: dict, replication_mode: list):
    """
    Modify all paired volumes at SRC to use Sync, Async or SnapshotsOnly replication type.

    SRC must be in readWrite mode with relationships to DST, so --src value matters.
    Sync replication type may noticeably degrade performance and will not work with inter-cluster latency over 8ms. Sub-5ms recommended. See latency value in cluster --list.
    Async is the default SolidFire type of replication and the SolidFire API creates Async pairings by default. Sub-20ms recommended. Maximum latency for Async replication is 8ms (see latency value in cluster --list).
    Snapshot-Only type of replication replicates only snapshots (enabled for remote replication) and nothing else. Recommended for low bandwidth, high latency (>5ms) connections.
    """
    if replication_mode[1] == []:
        logging.warning(
            "No volume IDs provided. All volumes will be set to" +
            replication_mode[0] +
            " replication mode.")
    logging.info("Modify paired volumes to use " +
                 replication_mode[0] +
                 " replication mode at SRC. SRC volume IDs: " + str(replication_mode[1]) + ". [] means ALL volumes.")
    paired_volumes = list_volume(src, dst, [])
    if replication_mode[1] == []:
        src_volume_ids = [item['localVolumeID'] for item in paired_volumes]
    else:
        src_volume_ids = []
        for i in replication_mode[1]:
            if i in [item['localVolumeID'] for item in paired_volumes]:
                logging.info(
                    "Volume ID " +
                    str(i) +
                    " found in list of currently paired volumes at SRC.")
                src_volume_ids.append(i)
            else:
                logging.error(
                    "Volume ID " +
                    str(i) +
                    " not found in list of currently paired volumes at SRC. Are you sure you got the right site or paired volume IDs? Exiting.")
                exit(200)
    s_params = {
        'volumeIDs': src_volume_ids,
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False}
    try:
        src_vol = src['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=s_params)['volumes']
        if src_vol == []:
            logging.error(
                "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
            exit(200)
    except common.ApiServerError as e:
        logging.error(
            "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
        logging.error("Error: " + str(e))
        exit(200)
    src_vol_mode = [v['access'] for v in src_vol]
    if list(set(src_vol_mode)) != ['readWrite']:
        logging.error("SRC volume access mode is not suitable for pairing. Specified SRC site volumes are in mode: " +
                      str(src_vol_mode[0]) +
                      ". Direction of replication must be from readWrite to replicationTarget. Changes must be made on the source where replication originates. Maybe you tried to change mode at DST? Exiting.")
        exit(200)
    if args.dry == True or args.dry == 'True' or args.dry == 'true' or args.dry == 'on' or args.dry == 'On' or args.dry == 'ON':
        logging.info(
            "Dry run on replication mode change is ON. Value: " + str(args.dry))
        print("\n===> Dry run: Replication mode of SRC volume IDs that would be changed to " +
              replication_mode[0] + " : " + str(src_volume_ids) + ".")
        logging.info(
            "DRY RUN on replication mode change for volumes at SRC. No changes will be made. Action would change SRC volume ID(s) " +
            str(src_volume_ids) +
            " to " +
            str(replication_mode[1]) +
            " while no changes would be done to DST volumes.")
    else:
        logging.warning(
            "Dry run on replication mode change for volumes at SRC is OFF. Value: " +
            str(
                args.dry) +
            ". Setting replication mode  to " +
            str(replication_mode[0]) +
            ".")
        for vid in src_volume_ids:
            try:
                src['sfe'].modify_volume_pair(
                    vid, mode=replication_mode[0])
                logging.info(
                    "Set replication mode on SRC volume " +
                    str(vid) +
                    " to " +
                    str(replication_mode[0]) +
                    ".")
            except common.ApiServerError as e:
                logging.error(
                    "Error setting replication status on SRC volume " +
                    str(vid) +
                    " to " +
                    str(replication_mode[0]) +
                    ". Exiting.")
                logging.error("Error: " + str(e))
                exit(200)

    return


def set_volume_replication_state(
        src: dict, dst: dict, replication_status: str):
    """
    Modify all paired volumes to pause or resume their replication.

    Works on volume pairs that are already paired. If DST is disconnected, status may change only on SRC.
    """
    if replication_status == 'pause':
        pause_replication = True
    elif replication_status == 'resume':
        pause_replication = False
    else:
        logging.error("Invalid desired replication state proposed. Exiting.")
        exit(200)
    paired_volumes = list_volume(src, dst, [])
    if len(paired_volumes) == 0 or paired_volumes is None or paired_volumes == []:
        logging.error("No paired volumes found. Exiting.")
        exit(200)
    src_volume_ids = [item['localVolumeID'] for item in paired_volumes]
    if args.dry == True or args.dry == 'True' or args.dry == 'true' or args.dry == 'on' or args.dry == 'On' or args.dry == 'ON':
        logging.info(
            "Dry run on replication status change is ON. Value: " + str(args.dry))
        print("\n===> Dry run: SRC volume IDs that would be changed to " +
              replication_status + " : " + str(src_volume_ids) + ".")
        logging.info(
            "DRY RUN on access property change for volumes at SRC. No changes will be made. Action would change SRC volume ID(s) " +
            str(src_volume_ids) +
            " to " +
            str(replication_status) +
            " and ignore mode of DST volumes.")
    else:
        logging.warning(
            "Dry run on replication state change for volumes at SRC is OFF. Value: " +
            str(
                args.dry) +
            ". Setting paused_manual to " +
            str(pause_replication) +
            ".")
        for vid in src_volume_ids:
            try:
                src['sfe'].modify_volume_pair(
                    vid, paused_manual=pause_replication)
                logging.info(
                    "Set replication status on SRC volume " +
                    str(vid) +
                    " to " +
                    str(replication_status) +
                    ".")
            except common.ApiServerError as e:
                logging.error(
                    "Error setting replication status on SRC volume " +
                    str(vid) +
                    " to " +
                    str(replication_status) +
                    ". Exiting.")
                logging.error("Error: " + str(e))
                exit(200)
    return


def reverse_replication(src: dict, dst: dict) -> dict:
    """
    Reverse direction of volume replication at SRC to inbound.

    Pausing / Resuming Volume replication manually causes the transmission of data to cease or resume.
    Changing access mode of replication causes the mode to change direction.
    """
    cluster_pair_name_id = src['sfe'].list_cluster_pairs().to_json()[
        'clusterPairs']
    if len(cluster_pair_name_id) != 1:
        for i in cluster_pair_name_id:
            logging.warning("Reviewing cluster pair ID: " +
                            str(i['clusterPairID']))
            if i['clusterName'] != dst['clusterName']:
                logging.error(
                    "Found Unconfigured cluster pairing or other pairing with another cluster on cluster " +
                    str(
                        src['clusterName']) +
                    ". Exiting.")
                exit(200)
            else:
                continue

    else:
        logging.info("Cluster pair ID should be DST cluster MVIP: " +
                     str(dst['mvip']) +
                     ". DST cluster MVIP of paired cluster is:" +
                     str(cluster_pair_name_id[0]['mvip']) +
                     " and pair ID against which we will verify is: " +
                     str(cluster_pair_name_id[0]['clusterPairID']) +
                     ".")
    paired_volumes = list_volume(src, dst, [])
    if len(paired_volumes) == 0 or paired_volumes is None or paired_volumes == []:
        logging.error("No paired volumes found. Exiting.")
        exit(200)
    src_volume_ids = [item['localVolumeID'] for item in paired_volumes]
    dst_volume_ids = [item['remoteVolumeID'] for item in paired_volumes]
    s_params = {
        'volumeIDs': src_volume_ids,
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False}
    d_params = {
        'volumeIDs': dst_volume_ids,
        'isPaired': True,
        'volumeStatus': 'active',
        'includeVirtualVolumes': False}
    try:
        src_vol = src['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=s_params)['volumes']
        dst_vol = dst['sfe'].invoke_sfapi(
            method='ListVolumes', parameters=d_params)['volumes']
        if src_vol == [] or dst_vol == []:
            logging.error(
                "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
            exit(200)
    except common.ApiServerError as e:
        logging.error(
            "Error getting volume information. Use --list to make sure the volumes exist and SRC and DST are correct. Exiting.")
        logging.error("Error: " + str(e))
        exit(200)
    s = 15  # 15 seconds grace period before action
    if list(set([v['access'] for v in src_vol])) == ['replicationTarget'] and list(
            set([v['access'] for v in dst_vol])) == ['readWrite']:
        logging.warning(
            "SRC is currently replicationTarget, DST is currently readWrite. Will reverse direction to make SRC readWrite and DST replicationTarget in " +
            str(s) +
            " seconds.")
        reverse_src_mode = 'readWrite'
        reverse_dst_mode = 'replicationTarget'
        logging.info(
            "All SRC and DST volumes are in consistent access mode. SRC: " +
            str(src_vol) +
            " DST: " +
            str(dst_vol) +
            ". Proceeding with reversal in " +
            str(s) +
            " seconds. Press CTRL+C to abort.")
        countdown(s)
    elif list(set([v['access'] for v in src_vol])) == ['readWrite'] and list(set([v['access'] for v in dst_vol])) == ['replicationTarget']:
        logging.warning(
            "SRC is currently readWrite, DST is currently replicationTarget. Will reverse direction to make SRC replicationTarget and DST readWrite in " +
            str(s) +
            " seconds.")
        reverse_src_mode = 'replicationTarget'
        reverse_dst_mode = 'readWrite'
        logging.info(
            "All SRC and DST volumes are in consistent access mode. SRC: " +
            str(src_vol) +
            " DST: " +
            str(dst_vol) +
            ". Proceeding with reversal in " +
            str(s) +
            " seconds. Press CTRL+C to abort.")
        countdown(s)
    else:
        logging.error("SRC and DST volumes are not in expected mode. SRC: " +
                      str(list(set([v['access'] for v in src_vol]))[0]) +
                      " DST: " +
                      str(list(set([v['access'] for v in dst_vol]))[0]) +
                      ". Exiting.")
        exit(200)
    if args.dry == True or args.dry == 'True' or args.dry == 'true' or args.dry == 'on' or args.dry == 'On' or args.dry == 'ON':
        logging.info(
            "Dry run on reversal of replication direction is ON. Value: " + str(args.dry) + ".")
        print("\n===> Dry run: volume IDs that would be changed to " +
              reverse_src_mode + " at SRC:", src_volume_ids)
        print("\n===> Dry run: volume IDs that would be changed to " +
              reverse_dst_mode + " at DST:", dst_volume_ids)
        logging.info(
            "DRY RUN on access mode reversal for volume pairs. No changes will be made. Action would change SRC volume ID(s) " +
            str(src_volume_ids) +
            " to " +
            str(reverse_src_mode) +
            " and DST volume ID(s) " +
            str(dst_volume_ids) +
            " to " +
            str(reverse_dst_mode) +
            ".")
    else:
        logging.warning(
            "Dry run on reversal of replication direction is OFF. Value: " + str(args.dry) + ".")
        if len(paired_volumes) < 500:
            try:
                src['sfe'].modify_volumes(
                    src_volume_ids, access=reverse_src_mode)
                dst['sfe'].modify_volumes(
                    dst_volume_ids, access=reverse_dst_mode)
                logging.info(
                    "Reversed access mode on SRC and DST. SRC Volume IDs: " +
                    str(src_volume_ids) +
                    ".")
            except common.ApiServerError as e:
                logging.error(
                    "Failed to reverse volume access mode on SRC and DST volumes. Please check and remedy. Exiting.")
                logging.error("Error: " + str(e))
                exit(200)
        else:
            logging.warning(
                "Many volumes found, pause, reversal and resume will be done one by one. Volume count: " +
                str(
                    len(paired_volumes)) +
                ".")
            for item in paired_volumes:
                try:
                    dst['sfe'].modify_volume_pair(
                        item['remoteVolumeID'], paused_manual=True)
                    src['sfe'].modify_volume_pair(
                        item['localVolumeID'], paused_manual=True)
                    logging.info("Paused replication on SRC volume ID: " +
                                 str(item['localVolumeID']) +
                                 " and DST volume ID: " +
                                 str(item['remoteVolumeID']) +
                                 ".")
                    dst['sfe'].modify_volume(
                        item['remoteVolumeID'], access=reverse_dst_mode)
                    src['sfe'].modify_volume(
                        item['localVolumeID'], access=reverse_src_mode)
                    logging.info("Reversed access mode on SRC volume ID: " +
                                 str(item['localVolumeID']) +
                                 " and DST volume ID: " +
                                 str(item['remoteVolumeID']) +
                                 ".")
                    dst['sfe'].modify_volume_pair(
                        item['remoteVolumeID'], paused_manual=False)
                    src['sfe'].modify_volume_pair(
                        item['localVolumeID'], paused_manual=False)
                    logging.info("Unpaused replication on SRC volume ID: " +
                                 str(item['localVolumeID']) +
                                 " and DST volume ID: " +
                                 str(item['remoteVolumeID']) +
                                 ".")
                except common.ApiServerError as e:
                    logging.error(
                        "Failed to reverse volume access mode on SRC and DST volumes. Please check and remedy. Exiting.")
                    logging.error("Error: " + str(e))
                    exit(200)
    return


def site(args):
    """
    Site-level actions for already paired SolidFire clusters.
    """
    if args.detach_site:
        detach_site(src, dst)
    elif args.set_access:
        if args.data is None:
            logging.error(
                "Access mode must be specified. Use --data 'readWrite' or --data 'replicationTarget'. Exiting.")
            exit(300)
        else:
            volume_access_property = access_type(args.data)
        if access_type == 'readWrite':
            logging.info("Desired access mode: " + volume_access_property)
        elif access_type == 'replicationTarget':
            logging.info("Desired access mode: " + volume_access_property)
        set_site_volume_access_property(src, dst, volume_access_property)
    else:
        logging.warning("Site action not recognized")
    return


def detach_site(src, dst):
    """
    Unilaterally remove cluster pairing between SRC and DST at SRC cluster.

    Leaves DST with broken cluster pairing relationship.
    """
    print("TODO: Remove cluster pairing at SRC.")
    return


def set_site_volume_access_property(src: dict, dst: dict, mode: str):
    """
    Modify all paired volumes on SRC to readWrite mode.

    Makes no changes on DST cluster. Use volume --reverse to reverse direction of replication (i.e. change mode on both sites).
    """
    paired_volumes = list_volume(src, dst, [])
    if len(paired_volumes) == 0 or paired_volumes is None or paired_volumes == []:
        logging.error("No paired volumes found. Exiting.")
        exit(300)
    src_volume_ids = [item['localVolumeID'] for item in paired_volumes]
    if args.dry == True or args.dry == 'True' or args.dry == 'true' or args.dry == 'on' or args.dry == 'On' or args.dry == 'ON':
        logging.info(
            "Dry run on unilateral access property change is ON. Value: " + str(args.dry))
        print(
            "\n===> Dry run: SRC volume IDs that would be changed to " +
            mode +
            " : " +
            str(src_volume_ids) +
            ".")
        logging.info(
            "DRY RUN on unilateral access property change for volumes at SRC. No changes will be made. Action would change SRC volume ID(s) " +
            str(src_volume_ids) +
            " to " +
            str(mode) +
            " and ignore mode of DST volumes.")
    else:
        logging.warning(
            "Dry run on unilateral access property change for volumes at SRC is OFF. Value: " +
            str(
                args.dry) +
            ".")
        if len(src_volume_ids) < 500:
            try:
                src['sfe'].modify_volumes(src_volume_ids, access=mode)
                logging.info(
                    "Set volume access mode on SRC volumes " +
                    str(src_volume_ids) +
                    " to " +
                    str(mode) +
                    ".")
            except BaseException:
                logging.error(
                    "Error modifying volume access mode on SRC volumes. This causes mismatch and may prevent storage access on one or more volumes. Exiting.")
                exit(300)
        else:
            logging.warning(
                "Over 500 volumes found. Pause, reversal and resume will be done one by one. Volume count: " +
                str(
                    len(src_volume_ids)) +
                ".")
            for item in src_volume_ids:
                try:
                    src['sfe'].modify_volume(item, access=mode)
                    logging.info(
                        "Set volume access on SRC volume ID: " +
                        str(item) +
                        " to " +
                        str(mode) +
                        ".")
                except BaseException:
                    logging.error(
                        "Error modifying volume access mode on SRC volume ID: " +
                        str(item) +
                        ". This causes mismatch and may prevent storage access on one or more volumes. Exiting.")
                    exit(300)
    return


def countdown(s: int):
    """
    Countdown timer for s seconds.
    """
    for i in range(s, 0, -1):
        print(i)
        time.sleep(1)
    return


def data_type(s):
    if s == '':
        return []
    try:
        return [tuple(map(int, item.split(','))) for item in s.split(';')]
    except BaseException:
        logging.error(
            "Pairs must be a semi-colon-separated list of comma-separated items (e.g. '1,51' or '1,51;2,52'). Exiting.")
        exit(4)


def account_data(s):
    try:
        return [tuple(map(int, item.split(','))) for item in s.split(';')]
    except BaseException:
        logging.error(
            "Account data must be a semi-colon-separated list of comma-separated items (e.g. '1,8;333,444'). Exiting.")
        exit(4)


def account_volume_data(s):
    try:
        try:
            s = s.split(';')
            return tuple(map(int, s[0].split(','))), [int(i)
                                                      for i in s[1].split(',')]
        except BaseException:
            logging.error(
                "Account IDs from SRC and DST must be semi-colon-separated from list of one or more comma-separated volume IDs (e.g. '1,8;330,331,332'). Exiting.")
            exit(4)
    except BaseException:
        logging.error(
            "Account data must be a semi-colon-separated list of comma-separated items (e.g. '1,8;333,444'). Exiting.")
        exit(4)


def access_type(s: str) -> str:
    if s == 'readwrite' or s == 'readWrite':
        return 'readWrite'
    elif s == 'replicationTarget' or s == 'replicationtarget':
        return 'replicationTarget'
    else:
        logging.error(
            "Volume access property must be one of 'readWrite' or 'replicationTarget', not " +
            s +
            ". Exiting.")
        exit(4)


def replication_data(s: str) -> list:
    data = [None, None]
    s = s.split(';')
    if s[0].lower() not in ['sync', 'async', 'snapshotsonly']:
        logging.error(
            "Replication mode must be one of 'Sync', 'Async', or 'SnapshotsOnly'. Exiting.")
        exit(4)
    else:
        data[0] = s[0]
    if s[1] == '':
        data[1] = []
        logging.warning(
            "Will change all volumes to specified replication mode.")
    try:
        data[1] = [int(i) for i in s[1].split(',')]
    except BaseException:
        logging.error(
            "Volume ID(s) must be a one or more integers following the first semicolon after the replication mode string, e.g. --data 'Async;55'. Exiting.")
        exit(4)
    if data[0] == 'Sync' or data[0] == 'sync':
        logging.warning("Replication mode set to Sync.")
        return ['Sync', data[1]]
    elif data[0] == 'Async' or data[0] == 'async':
        logging.info("Desired replication is Async.")
        return ['Async', data[1]]
    elif data[0] == 'SnapshotsOnly' or data[0] == 'snapshotsonly':
        logging.info("Desired replication is SnapshotsOnly.")
        return ['SnapshotsOnly', data[1]]
    else:
        logging.error(
            "Replication mode must be one of 'Sync', 'Async', or 'SnapshotsOnly', followed by a comma and one or more SRC volume IDs, e.g. 'Async;55,56'. Exiting.")
        exit(4)


def replication_state(s: str) -> str:
    if s.lower() not in ['pause', 'paused', 'resume',
                         'pausedmanual', 'resume', 'resumed']:
        logging.error(
            "Replication state 'pausedManual=True' is represented with 'pause' or 'resume'. Use --data 'pause'|'resume'. Exiting.")
        exit(4)
    if s == 'pause' or s == 'pausedManual' or s == 'Pause':
        return 'pause'
    elif s == 'resume' or s == 'Resume':
        return 'resume'
    else:
        logging.error("Replication mode must be one of 'pause', 'resume'.")
        exit(4)


def snapshot_data(s: str) -> list:
    s = s.split(';')
    try:
        if int(s[0]) < 1 or int(s[0]) > 720:
            logging.error(
                "Snapshot expiration time must be between 1h and 720h. Exiting.")
            exit(4)
        else:
            return [int(s[0]), s[1]]
    except BaseException:
        logging.error(
            "Snapshot data must be a semi-colon-separated list of integer and string (e.g. --data '168;my_snapshot'). Exiting.")
        exit(1)


def increase_volume_size_data(s: str) -> list:
    """
    Parses data string like '1073741824;100,200' and returns a list of two elements: added size in bytes and a list SRC/DST volume ID pair.
    """
    s = s.split(';')
    try:
        #
        if int(s[0]) < 1073741824 or int(s[0]) > 107374182400:
            logging.error(
                "This feature supports volume size growth 1-100 GiB at a time. Exiting.")
            exit(4)
        else:
            s[0] = int(s[0]) - int(s[0]) % 4096
            return [int(s[0]), [int(i) for i in s[1].split(',')]]
    except BaseException:
        logging.error(
            "Volume size data must be a semi-colon-separated list of integer and comma-separated list of volume IDs (e.g. --data '1073741824;100,200'). Exiting.")
        exit(4)


def upsize_remote_volume_data(s: str) -> list:
    """
    Parses data string like '100,200' and returns a list with two integer elements (SRC and DST volume pair IDs).
    """
    s = s.split(',')
    try:
        return [int(s[0]), int(s[1])]
    except BaseException:
        logging.error(
            "Volume ID data must be a comma-separated list of two integers (e.g. --data '100,200'). Exiting.")
        exit(4)


def report_data(s):
    # TODO: presently not in use
    pass


global src, dst

parser = argparse.ArgumentParser()

parser.add_argument(
    '--dry',
    type=str,
    default='off',
    help='Dry run mode. It is NOT available for all actions, so do not make the assumption that with --dry any action will have zero impact. Enable it with --dry on. Default: off.')
parser.add_argument(
    '--tlsv',
    type=int,
    default=None,
    help='Accept only verifiable TLS certificate when working with SolidFire cluster(s) with --tlsv 1. Default: 0.')
parser.add_argument(
    '--src',
    default=os.environ.get(
        'SRC',
        ''),
    help='Source cluster: MVIP, username, password as a dictionary in Bash string representation: --src "{ \'mvip\': \'10.1.1.1\', \'username\':\'admin\', \'password\':\'*\'}".')
parser.add_argument(
    '--dst',
    default=os.environ.get(
        'DST',
        ''),
    help='Destination cluster: MVIP, username, password as a dictionary in Bash string representation: --src "{ \'mvip\': \'10.2.2.2\', \'username\':\'admin\', \'password\':\'*\'}".')

subparsers = parser.add_subparsers()

cluster_parser = subparsers.add_parser('cluster')
cluster_parser.add_argument_group('cluster')
cluster_parser.add_argument(
    '--data',
    default='',
    help='Optional data input for selected cluster actions (where indicated in site action help). Not all cluster actions require or accept it.')

cluster_action = cluster_parser.add_mutually_exclusive_group(required=True)
cluster_action.add_argument(
    '--list',
    action='store_true',
    help='List cluster pairing between SRC and DST clusters. Requires paired SRC and DST clusters. Ignores --data because each cluster params are always available from --src, --dst.')
cluster_action.add_argument(
    '--pair',
    action='store_true',
    required=False,
    help='Pair SRC and DST for replication. Requires SRC and DST without existing pairing relationships. Multi-relationships are not supported. Ignores --data.')
cluster_action.add_argument(
    '--unpair',
    action='store_true',
    required=False,
    help='Unpair SRC and DST clusters. Requires SRC and DST in exclusive, mutual pairing relationship and no volume pairings. Ignores --data.')

cluster_parser.set_defaults(func=cluster)

volume_parser = subparsers.add_parser('volume')
volume_parser.add_argument_group('volume')
volume_parser.add_argument(
    '--data',
    default='',
    help='Optional data input for selected volume actions (where indicated in volume action help). Not all volume actions require or accept it.')

volume_action = volume_parser.add_mutually_exclusive_group(required=True)
volume_action.add_argument(
    '--list',
    action='store_true',
    help='List volumes correctly paired for replication between SRC and DST cluster. Requires paired SRC and DST clusters. Optional --data argument lists specific volume pair(s).')
volume_action.add_argument(
    '--pair',
    action='store_true',
    required=False,
    help='Pair volumes for Async replication between SRC and DST clusters. Takes a semicolon-delimited list of volume IDs from SRC and DST in --data (e.g. --data "111,555;112,600"). Requires paired SRC and DST clusters.')
volume_action.add_argument(
    '--unpair',
    action='store_true',
    required=False,
    help='Unpair volumes paired for replication between SRC and DST clusters. Requires paired SRC and DST clusters and at least one volume pairing relationship. Takes --data argument with only one pair at a time. Ex: --data "111,555".')
volume_action.add_argument(
    '--prime-dst',
    action='store_true',
    required=False,
    help='Prepare DST cluster for replication by creating volumes from SRC. Creates volumes with identical properties (name, size, etc.) on DST. . Takes one 2-element list of account IDs (SRC account ID,DST account ID) and another of volume IDs on SRC. Ex:  --data "1,22;444,555".')
volume_action.add_argument(
    '--mismatched',
    action='store_true',
    required=False,
    help='Check for and report any volumes in asymmetric pair relationships (one-sided and volume size mismatch). Requires paired SRC and DST clusters. Ignores --data.')
volume_action.add_argument(
    '--resize',
    action='store_true',
    required=False,
    help='Increase size of paired SRC and DST volumes by up to 1TiB or 2x of the original size, whichever is smaller. readWrite side must be on SRC cluster. Requires --data. Ex: "1073741824;100,200" adds 1 GiB to volume IDs SRC/100, DST/200. Default: "".')
volume_action.add_argument(
    '--upsize-remote',
    action='store_true',
    required=False,
    help='Increase size of paired DST volume to the same size of SRC volume, usually to allow DST to catch up with the size of SRC increased by Trident CSI. readWrite side must be on SRC side. Requires --data. Ex: --data "100,200" grows DST/200 to the size of SRC/100. Default: "0,0".')
volume_action.add_argument(
    '--reverse',
    action='store_true',
    required=False,
    help='Reverse direction of volume replication. You should stop workloads using current SRC (readWrite) volumes before using this action as SRC side will be flipped to replicationTarget and SRC iSCSI clients disconnected. Ignores --data.')
volume_action.add_argument(
    '--snapshot',
    action='store_true',
    required=False,
    help='Take crash-consistent snapshot of all volumes paired for replication at SRC. Use --data to specify non-default retention (1-720) in hours and snapshot name (<16b string). Ex: --data "24;apple". Default: "168;long168h-snap".')
volume_action.add_argument(
    '--set-mode',
    action='store_true',
    required=False,
    help='Change replication mode on specific SRC volumes ID(s) in active replication relationship to DST. Mode: Sync, Async, SnapshotsOnly. Example: --data "SnapshotsOnly;101,102,103". Requires existing cluster and volume pairing relationships between SRC and DST. WARNING: SnapshotsOnly replicates nothing if no snapshots are enabled for remote replication (create_snapshot(enable_remote_replication=True)).')
volume_action.add_argument(
    '--set-status',
    action='store_true',
    required=False,
    help='Set all SRC relationships to resume or pause state in --data. Ex: --data "pause" sets all SRC volume relationships to manual pause. --data "resume" resumes paused replication at SRC. (WARNING: applies to SRC, not DST).')
volume_action.add_argument(
    '--report',
    action='store_true',
    required=False,
    help='TODO: Report volume pairing relationships between SRC and DST, including mismatched and bidirectional. Requires paired SRC and DST clusters. Optional --data arguments: all, SRC, DST (default: all).')

volume_parser.set_defaults(func=volume)

site_parser = subparsers.add_parser('site')
site_parser.add_argument_group('site')
site_parser.add_argument(
    '--data',
    default='',
    help='Optional data input for selected site actions (where indicated in site action help). Not all site actions require or accept it.')
site_action = site_parser.add_mutually_exclusive_group(required=True)
site_action.add_argument(
    '--detach-site',
    action='store_true',
    help='Remove replication relationships on SRC cluster for the purpose of taking over when DST is unreachable. Requires paired SRC and DST clusters. WARNING: there is no way to re-attach. Disconnected cluster- and volume-relationships need to be removed and re-created.')
site_action.add_argument(
    '--set-access',
    action='store_true',
    required=False,
    help='Change access property on all SRC volumes with replication relationship to DST. Options: readWrite, replicationTarget (ex: --data "readWrite"). Requires existing cluster and volume pairing relationships between SRC and DST. WARNING: may stop/interrupt DST->SRC or SRC->DST replication.')
site_parser.set_defaults(func=site)

args = parser.parse_args()

if args.src is not None or args.dst is not None:
    try:
        src = ast.literal_eval(args.src)
        dst = ast.literal_eval(args.dst)
    except BaseException:
        logging.error(
            "Unable to parse SRC or DST. Review help and try again. Exiting.")
        exit(1)

if src['password'] == '':
    src['password'] = getpass("Enter password for SRC cluster (not logged): ")
if dst['password'] == '':
    dst['password'] = getpass("Enter password for DST cluster (not logged): ")

if args.tlsv == 1:
    src['tlsv'] = True
    dst['tlsv'] = True
    logging.info("TLS verification is ON.")
else:
    src['tlsv'] = False
    dst['tlsv'] = False
    logging.info("TLS verification is OFF.")
try:
    src['sfe'] = ElementFactory.create(
        src['mvip'],
        src['username'],
        src['password'],
        verify_ssl=bool(
            src['tlsv']),
        print_ascii_art=False)
    dst['sfe'] = ElementFactory.create(
        dst['mvip'],
        dst['username'],
        dst['password'],
        verify_ssl=bool(
            src['tlsv']),
        print_ascii_art=False)
except common.SdkOperationError as e:
    logging.error(e)
    exit(2)
except Exception as e:
    logging.error("Error: " + str(e))
    exit(2)
try:
    src['clusterName'] = src['sfe'].get_cluster_info().to_json()[
        'clusterInfo']['name']
    dst['clusterName'] = dst['sfe'].get_cluster_info().to_json()[
        'clusterInfo']['name']
    logging.info(
        "SRC cluster name: " +
        src['clusterName'] +
        " and DST cluster name: " +
        dst['clusterName'] +
        " obtained.")
except common.ApiServerError as e:
    logging.error("Error: " + str(e))
    exit(3)
except Exception as e:
    logging.error(
        "Error, possibly due to one or both clusters being unreachable: " +
        str(e))
    exit(3)

args.func(args)
