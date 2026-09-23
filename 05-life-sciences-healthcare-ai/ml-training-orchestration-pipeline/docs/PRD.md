# Product Requirements

## Problem

Training a model is usually a script someone ran once on a laptop. What
produced the artefact, on which data, with which hyperparameters, and whether
the current version is better than the last are all answered from memory — if
at all. Then the model is served from a file nobody can reproduce.

## Goal

A pipeline where training is triggerable, reproducible, observable and directly
connected to serving, with every run recorded.

## Users

| User | Need |
|---|---|
| The engineer iterating on the model | Change a hyperparameter, re-run, compare against every previous run |
| The engineer operating the service | Know whether a model is loaded, how fast it responds, and whether live inputs still resemble training data |
| Anyone consuming predictions | A stable HTTP contract that does not change when the model does |

## Functional requirements

| # | Requirement |
|---|---|
| F1 | Fetch a named dataset from the HuggingFace Hub |
| F2 | Clean it — drop nulls, filter implausible lengths — for both splits independently |
| F3 | Tokenise both splits and persist them in a re-usable format |
| F4 | Fine-tune a pretrained transformer with configurable hyperparameters |
| F5 | Evaluate on the held-out split: accuracy, weighted F1, precision, recall |
| F6 | Record every run — parameters, metrics, artefacts — to MLflow |
| F7 | Save a self-contained serving bundle |
| F8 | Trigger the whole pipeline from a single API call, without blocking the caller |
| F9 | Report the status of a run in progress |
| F10 | Serve predictions from the latest bundle |
| F11 | Expose request, error and latency metrics in Prometheus format |
| F12 | Compare live inference inputs against the training distribution |

## Non-functional requirements

| # | Requirement | Current state |
|---|---|---|
| N1 | Re-running an unchanged stage must not repeat its work | Met — Dagster asset materialisation |
| N2 | Training triggered over HTTP must not block the caller | Met — `BackgroundTasks` plus a polled `run_id` |
| N3 | Test suite must run without a GPU, a dataset or a trained bundle | Met — model and orchestration mocked |
| N4 | An untrained deployment must fail clearly, not silently | Met — `/predict` returns 503 with an actionable message |
| N5 | No credentials required to run the public path | Met — public dataset, local MLflow store |
| N6 | Training parameters bounded against resource exhaustion | **Not met** — no upper limits; tracked in ROADMAP |
| N7 | Concurrent training runs must not interfere | **Not met** — shared config file is rewritten in place |
| N8 | Inference must not block the event loop | **Not met** — synchronous forward pass in an async handler |

## Out of scope

- Distributed or multi-GPU training. One process, one device.
- A hosted MLflow tracking server. The local file store is the default.
- Model serving at scale. There is no batching queue, autoscaling or replica
  coordination — the in-memory run registry assumes a single instance.
- Automated retraining. Drift is measured, not acted upon.

## Success criteria

- A single API call takes an untrained system to a serving model.
- Every run is visible in both Dagster (what materialised) and MLflow (what it
  scored).
- Changing one hyperparameter re-runs only the stages that depend on it.
- The serving layer reports its own health, throughput and input drift.
