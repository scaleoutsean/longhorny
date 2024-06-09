- [Longhorny](#longhorny)
  - [What you **need to know**](#what-you-need-to-know)
  - [Production use](#production-use)
  - [Objectives](#objectives)
  - [Requirements](#requirements)
  - [How to run](#how-to-run)
    - [Cluster-scope actions](#cluster-scope-actions)
    - [Volume-scope actions](#volume-scope-actions)
    - [Site-scope actions](#site-scope-actions)
  - [Command examples](#command-examples)
    - [Cluster](#cluster)
  - [Volume](#volume)
  - [Miscellaneous stuff](#miscellaneous-stuff)
    - [PowerShell to help](#powershell-to-help)
    - [Site object (SRC, DST) and Longhorny CLI arguments](#site-object-src-dst-and-longhorny-cli-arguments)
    - [Volume objects on SolidFire](#volume-objects-on-solidfire)
  - [Testing and development environment](#testing-and-development-environment)
    - [Note on SolidFire SDK for Python](#note-on-solidfire-sdk-for-python)
  - [Random development notes](#random-development-notes)

# Longhorny

Longhorny is a script for SolidFire storage replication-related management. 

It grew out of my need to list cluster and volume pairs - which is something I've desired to add to [SFC v2](https://github.com/solidfire/sfc) - and other necessary and unnecessary stuff that was added as I got carried away. 

The code in this repository is permissively licensed, so feel free to use and modify within the terms of the permissive Apache License 2.0. With a bit of extra work you could use the elements of this script to modify it for multi-relationship clusters or other purposes (e.g. send these to Splunk, etc.).

## What you **need to know**

**The recommended action is `--list`**, while the rest may or may not work for you. While basic care has been taken to avoid creating problems, I am the only person who wrote and tested this script so far so I wouldn't run configuration-modifying actions against production clusters without prior testing. I myself only need the `list` action - okay, I need `mismatch` and `report` as well - while the others were added as convenience but may not be rock-solid.

Longhorny is is **limited to supporting a simple 1-to-1, exclusively paired clusters**. One SRC cluster, one DST cluster, one pairing. It is expected to reject actions when it spots either the source or the destination has another relationship, so in order to work with multiple clusters you'd have to modify the code.

## Production use

Apart from `--list` and other "no modifications" actions, I wouldn't just download Longhorny and use it in a production environment. But that doesn't mean it couldn't be used without issues. I'd recommend the following as a path to production use:

- DIY users: 
  - download SolidFire Demo VM (see [testing and development](#testing-and-development-environment))
  - [RTFM](https://docs.netapp.com/us-en/element-software/) 
  - read [NetApp Element Software Remote Replication - Feature Description and Deployment Guide (TR-4741)](https://www.netapp.com/media/10607-tr4741.pdf)
  - find a small and necessary scope, test, and see if it works for you. Modify or outsource if you can't do it on your own
- Enterprise: same as DIY, plus you can pay your systems integrator or NetApp to do that work for you

## Objectives

Longhorny's objective is to provide visibility into replicated SolidFire cluster and volume pairs - really just `list`-like actions, so that I can gather and send stuff to [SolidFire Collector](https://github.com/scaleoutsean/sfc) for SolidFire admins' viewing pleasure.

Everything beyond that is extra (and maybe nice to have, assuming it works), but that's also what makes it deserve a repository of its own as it has other uses. So far I've already done more than I expected and I decided to publish the script to see if anyone has uses for other actions and/or wants to contribute.

I am not committed to expanding or improving Longhorny but I may do it if I come up with new ideas for it. For example, recently I wrote a script for mapping Kubernetes/Trident volumes to SolidFire volume IDs (available in [Awesome SolidFire](https://github.com/scaleoutsean/awesome-solidfire)), so the output of that script (i.e. a list of a Kubernetes cluster's volume IDs) could be used as the input to Longhorny. Are you thinking what I'm thinking? You get the idea.

## Requirements

- SolidFire >=12.3 (also Element SDS, NetApp HCI storage)
- Python 3.10 (higher may 3.1x versions may be fine)
- SolidFire SDK Python >12.3 (see [notes on that](#note-on-solidfire-sdk-for-python))

## How to run

First we need to select one of the scopes (cluster, volume, site) and then one of the actions available in the scope (further below). Among the positional arguments below, `src` and `dst` are usually required for most actions.

```sh
usage: longhorny.py [-h] [--dry DRY] [--tlsv TLSV] [--src SRC] [--dst DST] [--data DATA] {cluster,volume,site} ...

positional arguments:
  {cluster,volume,site}

options:
  -h, --help            show this help message and exit
  --dry DRY             Dry run mode. It is NOT available for all actions, so don not make the assumption that with --dry any action will be zero impact. Enable with --dry on. Default: off
  --tlsv TLSV           Accept only verifiable TLS certificate when working with SolidFire cluster(s) with --tlsv 1. Default: 0
  --src SRC             Source cluster: MVIP, username, password as a dictionary in Bash string representation: --src "{ 'mvip': '10.1.1.1', 'username':'admin', 'password':'*'}"
  --dst DST             Destination cluster: MVIP, username, password as a dictionary in Bash string representation: --src "{ 'mvip': '10.2.2.2', 'username':'admin', 'password':'*'}"
  --data DATA           One or more semicolon-delimited volume ID pairs for cluster and volume actions between SRC and DST clusters. Optional in --list actions. Ex: "--data '158,260;159;261'
```

Note that `--dry` **is ignored** by many operations/actions. For example, every `--list` action ignores it. For more on `--dry` see the examples in which you're interested. If I remember correctly there are three of the more dangerous actions that consider `--dry on`, but additional actions may be made aware of it. Don't assume it's been implemented for everything that may be dangerous is all I'm saying. You may check the code and add it by yourself. 

There are `cluster`-, `volume`-, and `site`-level actions. For most of them you **must** provide a source (`--src`) and a destination (`--dst`). In some cases it is important that `--src` is really the source (i.e. the cluster where replication "originates" and where the volumes are read-write), so I encourage you to always verify that assignment.

If your "SolidFires" have snake-oil TLS certificates, just omit `tlsv` (TLS verification) to leave it as-is (to accept snake-oil TLS certificates). Obviously, that's not what you should do, but I know most will. If you want to upload a valid TLS certificate to SolidFire clusters, see [this](https://scaleoutsean.github.io/2020/11/24/scary-bs-postman-ssl-certs.html) or RTFM. It takes 5 minutes to do it and then you can use `--tlsv 1` and avoid MITM attacks.

Some actions require `DATA` to work with. When that's the case, use `--data DATA` to provide it. Data format for `DATA` varies, but Longhorny is mostly about volume-related actions so remember that volume pairs are provided as comma-delimited pairs (SRC, DST) and multiple pairs are delimited by semicolon. `"1,50;2,51"` is two SRC/DST pairs, (1,50) and (2,51), between SRC and DST (notice that if you were to swap SRC and DST with `--src` and `--dst`, then `"50,1;51,2"` would be equivalent to that in terms of the equivalence of outcome of a volume pairing action).

### Cluster-scope actions

```sh
usage: longhorny.py cluster [-h] (--list | --pair | --unpair)

options:
  -h, --help  show this help message and exit
  --list      List cluster pairing between SRC and DST clusters. Requires paired SRC and DST clusters. Does not require --data argument because cluster params are given in --src, --dst.
  --pair      Pair SRC and DST clusters for replication. Requires SRC and DST without existing pairing relationships - multi-relationships are not supported.
  --unpair    Unpair SRC and DST clusters. Requires SRC and DST in exclusive, mutual pairing relationship and no volume pairings.
```

`list` lists paired clusters. Harmless. 

`pair` changes cluster configuration on both sides: SRC gets paired with DST. No data is destroyed, but if this action succeeds SRC and DST (clusters) will be in a paired relationship.

`unpair` does the opposite from pair. It also changes cluster configuration on both sides, so be very careful if you have replication relationships set up. You shouldn't be able to `unpair` if there are valid replication pairs for volumes, but be careful with this action in any case.

### Volume-scope actions

```sh
usage: longhorny.py volume [-h] (--list | --pair | --unpair | --prime-dst | --mismatched | --reverse | --snapshot | --set-mode | --set-status | --report)

options:
  -h, --help    show this help message and exit
  --list        List volumes correctly paired for replication between SRC and DST cluster. Requires paired SRC and DST clusters. Optional --data argument lists specific volume pair(s).
  --pair        Pair volumes for Async replication between SRC and DST clusters. Takes a semicolon-delimited list of volume IDs from SRC and DST in --data. Requires paired SRC and DST clusters.
  --unpair      Unpair volumes paired for replication between SRC and DST clusters. Requires paired SRC and DST clusters and at least one volume pairing relationship.
  --prime-dst   Prepare DST cluster for replication by creating volumes from SRC. Takes one 2-element list of account IDs (SRC,DST) and another of volume IDs on SRC. Creates volumes with identical properties
                (name, size, etc.) on DST. Ex: --data "1,2;444,555"
  --mismatched  Check for and report any volumes in asymmetric pair relationships (one-sided and volume size mismatch). Requires paired SRC and DST clusters.
  --reverse     Reverse direction of volume replication. You MUST stop workloads using current SRC as readWrite will be flipped to replicationTarget.
  --snapshot    Take a crash-consistent snapshot of all volumes paired for replication at SRC and with expiration t+168 hours.
  --set-mode    Change replication mode on all SRC volumes in active replication relationship to DST. Options: Sync, Async, SnapshotsOnly (ex: --data "SnapshotsOnly"). Requires existing cluster and volume pairing
                relationships between SRC and DST. WARNING: SnapshotsOnly replicates nothing if no snapshots enabled for remote replication are taken at SRC (create_snapshot(enable_remote_replication=True)).
  --set-status  Set all SRC (WARNING: SRC, not DST!) relationships to resume or pause state in --data. Ex: --data "pause" sets all SRC volume relationships to pause.
  --report      Report volume pairing relationships between SRC and DST, including mismatched and bidirectional. Requires paired SRC and DST clusters. Optional --data arguments: all, SRC, DST (default: all).
```

Yeah, I know, I got carried away.

Ok, so `list` does the same thing as it for clusters - it also lists, only volumes. Harmless. `report`, below, is equally harmless.

`pair` pairs volumes. This may be disruptive! Say you have a workload on DST using Volume ID 52. Now you pair Volume ID 3 from SRC with Volume ID 52 from DST with `--pair "3,52"` and Longhorny yanks the volume from your workload at the destination site making it read-only (i.e. replicationTarget, which means read-only)! Yikes! Except Longhorny doesn't do that - it will reject to pair two volumes with the identical access property (readWrite, in this case). You'd have to set Volume ID 52 at the destination to replicationTarget before `pair` with DST/52 could do anything for you.

`unpair` does the opposite from `pair`. Longhorny **cannot know if the volumes you aim to unpair are in use**. To minimize the idiotic moves (present parties excluded), Longhorny does not accept more than one unpair pair (?) at a time. `--data "1,51;2,52 volume --pair` will work, but `--data "1,51;2,52 volume --unpair` shouldn't. But you can create a Bash loop and run Longhorny if you want to unpair many pairs at once. Unpaired volumes aren't "deleted" or anything like that, they're just unpaired.

`prime-dst` creates *new* volumes, but is a low action. As the help string says, its `DATA` format is different from regular `volume`-scope actions:

- The first element is a pair of integers: Account ID at SRC and Account ID at DST, e.g. `10,20;`
- The second is a list of integers, e.g. `101,102,103,104`: volume IDs owned by the first Account ID 10 from `--src` site

Therefore, `--src SRC --dst DST --data "10,20;101,102,103,104" volume --prime-dst` would take volumes 101-104 belonging to the account ID 10 at the SRC site and create very similar (apart from volume IDs, for example) volumes for the account ID 20 at the DST site. Then we could prepare those new volumes for pairing so that the source site's volume IDs 101-104 can be paired with (say) the destination site's volume IDs 40-43 using `--data "101,40;102,41;103,42;104,43 volume --pair`. Diff-priming the destination would be useful when a bunch of volumes are added to the source side, but I don't know if anyone has that problem so I haven't attempted to solve it.

Note that `prime-dst` doesn't change the new volumes at the destination to `replicationTarget`. Why's that? Because I don't know if you want to do that (you may want to do something else before you do that, such as import them to Hyper-V and log out of those targets before you flip them to replicationTarget), and because it's a more conservative approach. `prime-dst` can be risky if you provide a list of 5000 volumes and the destination runs out of 

`mismatched` aims to find mismatched volumes on both the source and destination cluster. Maybe one site's volume is bigger, SRC/101 is paired to DST/40, but DST/40 isn't paired to SRC/101, etc. The idea is if you have a bunch of volumes and things seem out of control, maybe `mismatched` can save you troubleshooting time.

`reverse` changes the direction of replication, so obviously this one is **dangerous**. If SRC is replicationTarget and DST is readWrite (that is, replication flows DST=>SRC), `reverse` flips that so that replication starts flowing SRC=>DST. This **may cause** unplanned downtime if you're not careful because flipping a volume from readWrite to replicationTarget disconnects all iSCSI clients, so if you issue this against the wrong `--src` and `--dst`, you may start getting calls, alerts and emails soon after that.

I think `volume --reverse`, as currently implemented, will really work only for rehearsals, when you have to run it once to try DST cluster, and then reverse again to return to SRC as "production". Why is there no ability to failover selected volumes?

- If you need to failover a handful of volumes no matter where the rest of them run, that's just 5 lines of PowerShell
- It's easy to take a list of IDs and failover just those volumes, but the next problem becomes when you want to flip the rest of them (or flip those back)? Who's going to figure out what should be replicated where? I think this can get messy quickly and at least with my level of skills (i.e. not high) I don't think I'd want to take on that task
- A simpler, safer and less ambitious idea is to use a smaller, dedicated script for dealing with groups of volumes. If you have 12 Kubernetes clusters and each Kubernetes admin runs their own script with their SolidFire storage account ID in `--data "${ACCOUNT_ID}"`, it's fine to offload all pairing and flipping to them. But if you do that then the SolidFire storage admin should in my opinion go into "100% read-only" mode and just use `list` and `report` send output to something like SolidFire Collector and observe in Grafana what the Kubernetes guys are up to

TODO: `snapshot` does what you think it does - it takes a snapshot to minimize potential damage before one makes a stupid move. Note that Longhorny never deletes volumes, so snapshots are safe from it. But if you mix in other code that deletes volumes or worse, snapshots may still be destroyed together with volumes by that other code (in which case we could take a site-replicating snapshot (we don't do that, as it may involve a surge of data replication), but then we may need to wait, etc. so ... no). Anyway, `DATA` settings are optional for `snapshot` action and by default it's taken with 168 hours (1 week) expiration time. You may override that with something like `--data "72;mysnap"` (expiration: `72` hours; snapshot name `mysnap`).

`set-mode` helps you change the default (Async) to other (Sync, or SnapshotOnly) mode. SolidFire's volume-pairing API method has Async hard-coded in it, so once remote pairing has been done you may use `set-mode` to change to another and back. RTFM and the TR linked at the top for additional details.

`set-status` pauses or resumes replication. If replication is going from DST=>SRC (i.e. DST side is read-write) and you need to pause replication at source if replication you would run `--src DST --dst SRC --data "pause" volume --set-status` (because DST is the source). That would put all volumes in manually paused state. Similarly, `--data "resume"` would resume. If you wanted to pause the destination (in this case, SRC)  you'd try `--src SRC --data "pause" volume --set-status`.

TODO: `report` is like `list`, completely read-only, except that it its result is slightly different. "Slightly???" Why do we need yet another action for that? List *actually* lists volume pairing relationships, whereas `report` reports on volume pairings, and if I wanted to see what's misconfigured or broken, `report` may give me that whereas `list` may not. Given that both INs and OUTs are very different, I don't want to bloat `list` to 500 lines of code.

### Site-scope actions

**CAUTION:** these may be **dangerous**. I'm not sure there's a strong case for them, so they are work-in-progress and may not care about `--dry on`. I would advise against using them without prior testing of the exact scenarios you aim to deal with or visual code inspection.

```sh
usage: longhorny.py site [-h] (--detach-site | --set-access)

options:
  -h, --help     show this help message and exit
  --detach-site  Remove replication relationships on SRC cluster for the purpose of taking over when DST is unreachable. Requires paired SRC and DST clusters. WARNING: there is no way to re-attach. Disconnected
                 clusters and volumes need repairing from scratch.
  --set-access   Change access property on all SRC volumes with replication relationship to DST. Options: readWrite, replicationTarget (ex: --data "readWrite"). Requires existing cluster and volume pairing
                 relationships between SRC and DST. WARNING: may stop/interrupt DST->SRC or SRC->DST replication.

```

TODO: `detach-site` attempts to remove replication configuration from --src (`--src SRC`). 

`set-access` changes access mode on volumes paired for replication **at the source**. To change access mode for the other site, use `--src OTHER`.

When I started working on site actions I thought they may be useful, but later I realized it can be a slippery slope. For example, the remote site DST may or may not be offline. If it's offline (or for whatever reason unreachable), site actions will not be able to work as they attempt to connect to `--dst` as well which means actions may not be useful for their main use case.

So, as-is, they can't work without Longhorny connecting to DST although `site` actions don't *do* anything to `--dst` site. But `site` actions *may* need to get some information from DST, so the next question is do we want to change the requirement for `--src --dst` when an action is a site-level action and maybe work without some information we need or limit ourselves to the situation where both sites are reachable. For time being I chose to leave the `--dst` requirement in place. Remember that even if you don't supply `--dst DST`, Longhorny may configure `--dst` with `DST` from your OS environment if you've set it.

## Command examples 

If you're not sure how something works, I may post all examples and details in a demo video which I'll link from here as well. 

But more importantly, I wouldn't suggest to anyone to use Longhorny on real clusters without having own VM-based sandbox where experimentation may be done freely.

### Cluster

Checks if SRC and DST are paired and if so, outputs pairing configuration.

**Pair clusters** without offering the passwords, so that you get prompted to enter them:

```sh
~$ ./longhorny.py --src "{ 'mvip': '192.168.1.30', 'username':'admin', 'password':''}" --dst "{ 'mvip': '192.168.105.32', 'username':'admin', 'password':''}" cluster --pair
Enter password for SRC cluster: 
Enter password for DST cluster:
```

See [towards the bottom](#site-object-src-dst-and-longhorny-cli-arguments) for other ways to provide `--src` and `--dst` values to Longhorny.

**List** cluster pairing, if any:

```sh
longhorny cluster --list
```

Output:

```raw
{'PROD': [{'clusterName': 'DR',
           'clusterPairID': 55,
           'clusterPairUUID': 'b9322478-3779-4cd3-908f-2a48f22202fe',
           'clusterUUID': 'bgn0',
           'latency': 1,
           'mvip': '192.168.105.32',
           'status': 'Connected',
           'version': '12.5.0.897'}],
 'DR': [{'clusterName': 'PROD',
         'clusterPairID': 61,
         'clusterPairUUID': 'b9322478-3779-4cd3-908f-2a48f22202fe',
         'clusterUUID': 'wcwb',
         'latency': 1,
         'mvip': '192.168.1.30',
         'status': 'Connected',
         'version': '12.5.0.897'}]}
```

What's what? Apart from the very obvious:

- `clusterPairUUID` is the unique ID of the pairing relationship, specific to this and only this pairing relationship. It's expected to be the same for each cluster
- `latency` (ms) - this guides us in determining appropriate replication mode (e.g. 1ms is good for Sync, 10ms is not)
- `status` - `connected` is good, `connecting` is good for the first 5 seconds and after that may indicate firewall or other network problems (see the NetApp TR at the top, RTFM, etc.)

Longhorny lists cluster pairing only for SRC and DST and only if SRC and DST both have one and only one relationship that is mutual and completely configured (as in, not "pending", etc.).

If nothing is returned, then they're not properly paired. If you try and set it up with `cluster --pair` or from the Web UI both of those can work but only if neither SRC and DST have any other relationships.

Longhorny can't get into a situation where SRC or DST get paired when either side has existing relationship(s). You *can* set those up later on your own, but then `cluster --list` and other commands may stop working because it tries to detect, and reject to do anything, in such situations.

Longhorny won't pair SRC and DST if either SRC or DST has anything but 0 existing cluster relationships, or if SolidFire rejects it (due to network problems, different major version of Element OS, etc.). Review the error, SolidFire KBs, docs, etc. and try to fix it.

**Unpair clusters** works regardless which site is provided as the source and which as the destination, as it checks both sides to make sure there's one and only one relationship on each.

```sh
longhorny --src SRC --dst DST cluster --unpair
```

Longhorny's `cluster --unpair` won't unpair SRC and/or DST cluster if:

- either SRC or DST has anything but one and only one cluster pairing and the paired party is the other cluster
  - Example 1: cluster DST is paired with cluster SOME - fail (no can do)
  - Example 2: clusters SRC and DST have a pending peering relationship: fail. Delete that pending relationship and re-try
- there are existing volume replication pairs
  - Longhorny fails for any as we want to avoid accidental unpairing of relationships with some other cluster involved

## Volume

`volume --list` does what you think it does: given a SRC and a DST cluster, it checks if cluster pairing is in place and spits out a list of properly paired volumes between them. Remember, there's no "direction" in this configuration: SolidFire replication is readWrite to replicationTarget, so to know what's replicated to what, you won't find that in this output here. This lists volume pairing relationships (and that's why I'm thinking to add `volume report` action).

```raw
[{'clusterPairID': 55,
  'localVolumeID': 158,
  'localVolumeName': 'test',
  'remoteVolumeName': 'testr',
  'remoteReplicationMode': 'Async',
  'remoteReplicationPauseLimit': 3145728000,
  'remoteReplicationStateSnapshots': 'PausedDisconnected',
  'remoteReplicationState': 'PausedDisconnected',
  'remoteVolumeID': 260,
  'volumePairUUID': '44df1d5e-8694-4ed1-bdaf-fa773fb9b165'},
 {'clusterPairID': 55,
  'localVolumeID': 164,
  'localVolumeName': 'srcorig',
  'remoteVolumeName': 'dstorig',
  'remoteReplicationMode': 'Async',
  'remoteReplicationPauseLimit': 3145728000,
  'remoteReplicationStateSnapshots': 'PausedDisconnected',
  'remoteReplicationState': 'PausedDisconnected',
  'remoteVolumeID': 391,
  'volumePairUUID': '3406d44a-081c-4841-8838-46f14feaac5e'}]
```

Both volume relationships are Async, the pairs are `[(158,260),(164,391)]`. If we wanted to `pair` these we'd do `--data "158,260; 164,391"`.

**Pair volumes** for replication. To replicate volume IDs 1 and 2 from site SRC to site DST, you need DST volumes to exist prior to running this action and they must have some identical properties and one different property:

- Same volume size in bytes (`volume['totalSize']`)
- Same volume block size (4096 or 512e) (`volume['blockSize']`)
- *Opposite* access mode (that is, while the source side must be `readWrite`, the destination must be `replicationTarget`)

You may also want the same QoS settings or QoS Policy contents, but that's optional.

```sh
longhorny --src SRC --dst DST --data "1,44;2,55" volume --pair
```

Another reminder about the direction of replication: volume IDs 1 and 2 exist at SRC so assumed that `--src` is readWrite. To replicate in the opposite direction, use `--src REMOTE` and provide the remote volume IDs as the first element of each `DATA` pair.

No account ID, QoS settings or other non-essential details are asked for because in this action the destination volumes must already exist and this Longhorny `volume` level operation does not touch storage account assignment or modify any volume settings except the replication-related settings (pair, unpair, reverse, etc.). Only `--prime-dst` can create new volumes, but even that action does not delete volumes.

If there's no cluster peering between SRC and DST cluster, volume pairing operation will fail immediately. SolidFire requires cluster peering to be in place before volume pairs can be configured.

**Reverse replication direction** with `--reverse` action.

**Important assumption**: in this scenario I assume the entire cluster of something (Hyper-V, etc) needs to be switched to the site of destination, and **all paired volumes need to be reversed** and activated there. There's no attempt to take a list of volume IDs, some account ID or whatever and failover just two volumes for one database or an individual account's volumes (see [PowerShell](#powershell-to-help) examples for these "small scope" actions). Don't use this action if you want to failover just some of the paired volumes.

If you change access status to replicationTarget all existing iSCSI connections to the volume are instantly terminated. You should stop workloads on the site that needs to change to replicationTarget mode or they'll be disconnected anyway (which is disruptive to clients using the volume(s)). Also expect some routine OS-level errors on the host side if they remain logged into targets switching to replicationTarget access mode, but those can likely be ignored as long as volumes going to replicationTarget mode have been dismounted (although they may still be logged on by the host).

I assume that in normal life if replication is flowing from `--src SRC` to `--dst DST`, no one will try reverse the direction *unless* they can't access SRC. So as far as the risk of reversing in the wrong direction is concerned, it's rather small: SRC goes down, you won't be able to "reverse" anyway because Longhorny won't be able to connect. You'll have to manually select all volumes set to replicate from SRC to DST, pause that replication, and switch the DST side to readWrite. 

**Prime destination volumes** when you're setting up a DR site and have many volumes to create at the destination at once.

- Pair clusters if they aren't paired
- Prime the DST cluster
- Pair a bunch of volumes

Priming does the following:
- List all SRC volumes which we intend to replicate
- Get the volumes' properties and recreate the same on the DST cluster for provided Account ID (that exists at the destination)

Priming requires two mandatory and one optional input:

- (required) pair of accounts IDs; one from the source (to whom the volumes belong) and one from the destination, to whom the new volumes should be assigned
- (required) list of volume IDs from the source - their properties will be used to create volumes at the remote site

Find **mismatched** volumes with `volume --mismatched`. I may still modify the format of this response, but basically it gives a view from the source vs. a view from the destination and - if the views aren't symmetric - a warning that makes it easier to figure it out may be logged at the end.

```raw
[(158, 260), (163, 390), (164, 391)] 
[(260, 158), (262, 162), (390, 163), (391, 164)]
WARNING:root:Mismatch found at DST: vol ID 262 in relationship a8051542-9a13-4d73-bb7f-7110483b70f4 found at DST, but paired volume ID at SRC not found: 162
```

**Unpair volumes** is a sensitive operation. Although it "only" unpairs and doesn't delete volumes, it's suggested to use it with `--dry on` (default is `off`!) before actually letting it remove a pairing.

```sh
longhorny -dry on --data "167,393" volume --unpair
```

With `--dry on`, we only get a "preview" similar to this:

```sh
Remove data tuple: [(167, 393)]
===> Dry run: volume IDs that would be removed (SRC, DST): [(167, 393)]
```

## Miscellaneous stuff

### PowerShell to help

I mentioned several times how `site`-level commands (currently) may not be able to do anything meaningful without the ability to connect to the destination API, and that I'm still thinking what to do about that.

The problem is the logic of such workflows can become very complicate, but if you know what the situation is and what you want to do, it's to  suspend replication on all volumes at one site from Python or PowerShell. Since SolidFire CLI (in Python) is no longer maintained and PowerShell is superior, I'll use this section to give simple PowerShell examples for folks who need to perform quick actions.

**CAUTION:** this pauses replication on *all* paired volumes on the cluster you're connected to and goes **without confirmation**. 

```powershell
Get-SFVolumePair | Set-SFVolumePair -PausedManual $True
```

Fun fact I just discovered: `Get-SFVolumePair` output doesn't even show any difference "before vs. after" as far as replication state is concerned. We have to use `Get-SFVolumePair | ConvertTo-Json` to see it, which helps the cause for `--data 'pause' volume --set-status` (if its output can be made easier to view and use).

To go back, simply reverse.

```powershell
Get-SFVolumePair | Set-SFVolumePair -PausedManual $False
```

The reason this is simple is we know exactly what we want to do, we don't care about the other site, and there are no if/else scenarios. Just flip 'em here and now. 

Flipping the surviving site's access mode from replicationTarget to readWrite is also very easy when that's the only thing that has to be done.

```powershell
Get-SFVolumePair | Set-SFVolume -Access readWrite
```

If you do `-Confirm:$False` then it just goes on and flips the entire site to readWrite, which is fine if the other site is dead and you can't properly reverse with `volume --reverse`, for example.

To filter out (or in) just selected volumes:

```powershell
PS > Get-SFVolume | Select-Object -Property VolumeID,Name | Where-Object -Property Name -Match "pvc-*"

VolumeID Name
-------- ----
      59 pvc-ba3213cd-01bc-4920-b1c7-708ed89e5730
     111 pvc-8d31e43b-f942-4cf8-94db-a08762c745ee
     112 pvc-14a51322-16c8-4b95-a7e4-28d9963450b3
     113 pvc-4fb5d7f5-4d98-429e-ab36-1b2118b7e55c
     115 pvc-fc799089-9559-4d97-84c8-d98e9dfbf884
     116 pvc-a7b61fe0-7e9d-40f4-bc06-9c1623adade4
     117 pvc-9812208f-72f5-41d8-9348-4fb42db8e6af
     120 pvc-bd1254e7-4102-4b58-960c-70be158c75fc
     121 pvc-58d35404-479b-4c5d-a67b-d96521f63ce2
     122 pvc-afc3936c-9cd4-47bb-bdf1-b1c46fd910ad
     123 pvc-c47a3f9f-4628-4e3b-8a86-313ec02f49b4
     124 pvc-515bccf3-577b-4149-9633-9da86913c933
     125 pvc-910cc289-64b8-4cc9-a411-524fd713d950
     127 pvc-a9531e89-7900-4265-9910-030142b4646a
     133 pvc-4bf6f5e2-bd1c-4908-88d0-62ecd66f6d33
     139 pvc-d793176f-2484-48ea-9255-f70215a7c5f7
     157 pvc-a5f21571-e002-493f-b2dc-df01f40c1fa1
```

We can pipe that to `Set-SFVolume` or store that result in a variable, e.g. `$kvols`, and then pipe that to some other command:

```powershell
$kvols.VolumeID | Set-SFVolume -Access readWrite
```

Again, 2 lines vs. 100 when you have to consider a variety of other possibilities. 

That's why there's no urgency to further develop `site`-level commands, although it'd be nice if I had some ideas about specific use cases which I'd want to address with Longhorny.

### Site object (SRC, DST) and Longhorny CLI arguments

SRC and DST are KV pairs of SolidFire mvip and two credential-related fields, i.e. `mvip`, `username`, and `password`.

There are several more or less frustrating ways to provide these to Longhorny.

I like this one, because to swap SRC and DST I just change the three letters in each of `--src` and `--dst`, but if you run several commands this way, sooner or later you'll forget to change back and execute a command against the wrong site.

```sh
longhorny --src "{ 'mvip': '192.168.1.30', 'username':'admin', 'password':'*******'}" --dst "{ 'mvip': '192.168.105.32', 'username':'admin', 'password':'*******'}" cluster --list
```

Alternatively, paste your config to shell variables SRC and DST before running.

```sh
SRC="{ 'mvip': '192.168.1.30', 'username':'admin', 'password':''}"
DST="{ 'mvip': '192.168.105.32', 'username':'admin', 'password':''}"
longhorny cluster --list
Enter password for SRC cluster: 
Enter password for DST cluster: 
```

Longhorny loads `--src` from the OS environmental variable SRC and `--dst` from DST. This is probably the worst way because you don't even see 'em. You can verify what you are about to run 10 times and still run it against the wrong site.

For me the best way to run Longhorny is:

- Two shell terminals (one dragged to left (or to the top) and the other to the right (or to the bottom))
- The left has `--src SRC --dst DST`, the right has `--src DST --dst SRC` (with or without password value provided in the site object string)

Then you just go to the right window and as long as you don't copy over *entire* lines (with the wrong --src and --dst in them), you can be fine.

Then Longhorny uses SolidFire Python SDK to establish a connection to each site.

### Volume objects on SolidFire

A SolidFire volume may be identified by volume ID (integer) or name (integer or string). The former is guaranteed to be unique, while the latter is not.

Many sites do not have duplicate volume names (within the site), but they *may* have them - e.g. in different KVM clusters - and it shouldn't be happening. Instead, some naming conventions should be used (e.g `clusterName-teamName-volumeName`).

Volume ID is guaranteed to be unique per cluster. That's why Longhorny only uses volume IDs while names *may* be provided in logs or output, but are never used in anything that changes SolidFire configuration.

## Testing and development environment

For production use, I strongly recommend having two single-node test clusters.

- The SolidFire API is unlikely to change at this point, but iSCSI client behavior or Python or other bits and pieces 
- If you use Kubernetes, that is a fast-moving target, and then there's also NetApp Trident. Sometimes major changes happen in months, so having a testbed where you can compare results of before, after various upgrades is mandatory

Here's what you need for testing and development:

- Two mid-sized VMs for SolidFire "sites" - 2 x 16 GB RAM (NOTE: SolidFire Demo VM is an OVA file, and if you don't have VMware you can use the free ESXi 7, deploy it to KVM or Hyper-V, and deploy OVA to ESXi VM - needs 16 GB per VM)
- Two mid-sized VMs for compute "site" resource, e.g. Hyper-V, KVM, Kubernetes, etc. - 2 x 16 GB RAM

You can get the free SolidFire Demo VM from NetApp Support (login required). It's limited to 100 volumes - more than enough for testing. SolidFire Demo VM allows multiple storage accounts (each being a different iSCSI client), so just two SolidFire VMs can accommodate testing with several VMs simulating different Kubernetes or other clusters at each "site" (VM group). SolidFire Demo VM is well-behaved and an excellent tool for test/development as long as you don't need high performance (it's limited to 3000 IOPS).

### Note on SolidFire SDK for Python 

As of now it's a mess because SolidFire SDK 12.3.1 was released, but there are several bugs that impact methods used by Longhorny, and you must install it with `python3 setup.py` (and even then it will still claim it's 12.3.0.0).

- [Update version-related info and publish on PyPi](https://github.com/solidfire/solidfire-sdk-python/issues/60)
- [Usage of dash-separated 'description-file' will not be supported starting Sep 26, 2024](https://github.com/solidfire/solidfire-sdk-python/issues/65)

Older versions are available on `pip`, but may have other bugs.

See the Github [issues](https://github.com/solidfire/solidfire-sdk-python/issues) for more.

## Random development notes

If you spot some "inconvenient" behavior or logic, it exists because I couldn't make it more "convenient" while being careful. If something "looks wrong", Longhorny doesn't try to be smart and "handle it for you". Instead, it prefers to exit and let you figure it out yourself. 

It's easier to fix or review what Longhorny complained about than figure out what the heck just happened to 245 of your production volumes. Longhorny attempts to never do what you didn't unambiguously tell it to do.

But, pull requests that improve the code and eliminate bugs are welcome.

Some notes on the script itself: it's not DRY - because I didn't set out to write all those similar actions at first and was lazy to DRY the code after that - and tests are missing - because there are currently just 0 users and I am busy and don't have time to learn how to write parametrized tests.

Unlike in SFC v2 (where I've removed SolidFire Python SDK), here I used SolidFire Python SDK as the "default" and standard tool widely used by those who have more than one cluster.