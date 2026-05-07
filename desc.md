claude, we will be moving finipipe to gcp, consolidating resources, automating processes, altering our setup. 

right now we have a few components. we have infra which should provision resources and set up infra. right now we have them as python files that provison and setup the resources. we will want to move this to gcp with the gcloud cli. i will share files with you of where to look beacuse the architecture is going to change. 

we have front end which wont change. 

we have deploy that will be similar. we will want all of our compute resources to be a docker compose file. will need to make the correct docker files and make a secrets loading sript for automated setup.

we will then have dagster which will be out orchestration engine. i still need to figure out how we are going to format this such that we can have clean code loading pyspark jobs etc. it will be changeing from aws to gcp as well. we wil be using dataproc, gcs, icebeg, bigquery, and cloudrun.

i would like to move away from the chomor achritecurre because that doesn't make sense to me. 

also i think back end needs to be rearchitected but the general idea will remain the same. 

can we start to create a plan.

i would like us to have a git branch called gcp for all of these changes that we will eventually merge to main.

for looking at some of the gcp stuff take a look at ./gcp-finpipe for some of that