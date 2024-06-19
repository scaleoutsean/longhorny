## Longhorny Step-by-Step Tutorial

If Longhorny's 'README.md is too long or incomprehensive, here's a hopefully simple, step-by-step tutorial for the initial release. I won't necessarily update it, but refer to online help if some things don't work.

Download the free SolidFire Demo VM OVA file. If necessary (Hyper-V, KVM) install ESXi 7 to nest SolidFire VMs in it. You'd need around 18 GB per each VM. Configure two SolidFire "sites" and install SolidFire SDK for Python to use Longhorny.

Modify the below to your MVIPs and usernames.

```sh
export SRC="{ 'mvip': '192.168.1.30', 'username':'admin', 'password':''}"
export DST="{ 'mvip': '192.168.1.30', 'username':'admin', 'password':''}"
```

Verify Longhorny works. You should be prompted for passwords as we did not export them in the two lines above (you can do that if you don't want to re-enter them every time).

```sh
./longhorny.py cluster --list
```

Pair clusters (identified by SRC and DST, above). This won't work if they have empty pairing configuration when you run.

```sh
./longhorny.py cluster --pair
```

View:

```sh
./longhorny.py cluster --list
```

Assuming SRC cluster has volume IDs 163, 164 (in readWrite mode) and DST has identically-sized 390, 391 (in replicationTarget mode). Pair them:

```sh
./longhorny.py volume --pair --data "163,390;164,391"
```

Note the storage tenant (account) IDs you decided to use. Let's say it's 13 at the source, and 3 at the destination. We want to continue with this arrangement to not get lost in complexity.

Create another readWrite volume for account ID 13 at the source. Say this volume ID is 169.

Now prime the destination. (13,3) means source account 13 and destination account 3. 169 is the new volume at the source.

```sh
./longhorny.py volume --prime-dst --data "13,3;169"
```

This should create a new "identical" volume at the destination, let's say it's volume ID 500. Now you can pair it without extra work.

```sh
./longhorny.py volume --pair --data "169,500"
```

Now "`cluster --unpair`" should not work because at least one volume pairing is in place. Try and make sure of it.

```sh
./longhorny.py cluster --unpair
```

Let's continue with volume-level actions.

If you don't need Async for this pairing, you can use the bandwidth-saving SnapshotsOnly by identifying the source volume in a paired relationship by its ID.

```sh
./longhorny.py volume --set-mode --data "SnapshotsOnly;169"
```

Before trying to failover to the remote site, stop workloads on paired volumes at the source side and take a snapshot of all paired volumes on the site specified in `--src`. "`1;temp`" means 1-hour retention and the snapshot name "temp".

```sh
./longhorny.py volume --snapshot --data "1;temp"
```

To test failover and make the remote site "active" (readWrite):

**CAUTION:** this cuts off iSCSI access to all clients that use **paired volumes** at the site specified in `--src`! Other (non-paired) volumes at the source site should remain unaffected.

```sh
./longhorny.py volume --reverse
```

As I've mentioned above, you SHOULD have all the workloads that use the source side paired volumes stopped before this because the reverse action will flip all paired volumes from that site to replicationTarget i.e. read-only mode.

To fail back, you can do the same thing in reverse: at the remote site first stop remote workloads on replicated volumes, take a local site snapshot (at the remote site), and then reverse to fail back to the original, primary site.

