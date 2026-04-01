---
title: orchestration
order: 4
---

dagster manages the full pipeline lifecycle. sensors monitor for new data, jobs handle backfills (sequential or parallel), and the platform provisions ec2 instances, runs workloads via ssm, and terminates resources automatically when complete.
