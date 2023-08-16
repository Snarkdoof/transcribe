# Installing Transcode

## Root node
First install CryoCore and CryoCloud (https://github.com/Snarkdoof/cryocore)

Install nginx with ssl sertificates (certbot is good)

```
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot -d <yourdomain> --nginx
```

Create your web directory (set it up properly too, the default is /var/www/html).

Set config for the transcode:
```
ccconfig add Cryonite.NetTranscriber.model large-v2
ccconfig add Cryonite.NetTranscriber.webroot /var/www/html/transcribe
ccconfig add Cryonite.NetTranscriber.weburl https://<yourdomain>/transcribe/
```

Model can also be a local file, as long as whisper-timestamped can use it.


## Worker node
In order to use automatic starting, ensure that this command succeeds from the
root node, and ensure that the name of the node is correct in
nettranscribe.json (it must be on the machine that can run gcloud, default is *ccroot*), and that the instance name of your processing machine is set (default is *instance-1*).

```
# If not logged in
gcloud auth login 

gcloud compute instances list
```

The instance mentioned in the "start" clause in the gcloud module in nettranscribe.json must be listed by the gcloud list command.

Open for remote connections on the root node for remote mysql connections, change the listen port to the local IP above, add user and grant access to cryocore.* to the user.

```
# Something like this

CREATE USER 'cc'@'workernodenameorIP' identified by 'yourpassword for mysql';
GRANT ALL ON cryocore.* to 'cc'@'workernodenameorIP';
FLUSH PRIVILEGES;
```

You should now be able to connect with mysql -u cc -p <IP of root> cryocore from the worker node.

On the worker node, install cryocore and cryocloud as mentioned earlier.
Edit ~/.cryoconfig and make it look something like this, using the IP on your root node.
```
{
  "db_host": "10.128.2.12"
}
```

Set up shared filesystem:
Make the mount point /data and set cryocore as owner.

Add to your fstab somethig like
```
<ipofrootnode>:/data /data nfs defaults 0 0
```

Now you might need dockers and GPU support for that, so just hammer on Google and try all the black magic you can find to make that work.  When 
```
docker run --rm  --gpus all nvidia/cuda:11.6.2-base-ubuntu20.04 nvidia-smi
```
runs without errors as the cryocore user, you are good!

