//go:build !no_antithesis_sdk

// -*- Mode: Go; indent-tabs-mode: t -*-

/*
 * Copyright (C) 2026 Canonical Ltd
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

package state_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	. "gopkg.in/check.v1"
	"gopkg.in/tomb.v2"

	"github.com/snapcore/snapd/overlord/state"
)

func (ts *taskRunnerSuite) TestAcceptedAbortAssertion(c *C) {
	if os.Getenv("SNAPD_TEST_ACCEPTED_ABORT") != "" {
		st := state.New(nil)
		st.Lock()
		change := st.NewChange("install", "...")
		task := st.NewTask("blocking", "...")
		change.AddTask(task)
		task.SetStatus(state.DoingStatus)
		change.Abort()
		c.Check(task.Status(), Equals, state.AbortStatus)
		st.Unlock()
		return
	}

	outputPath := filepath.Join(c.MkDir(), "sdk.jsonl")
	cmd := exec.Command(os.Args[0], "-test.run=^TestState$", "-check.f=^taskRunnerSuite.TestAcceptedAbortAssertion$")
	cmd.Env = append(os.Environ(),
		"SNAPD_TEST_ACCEPTED_ABORT=1",
		"ANTITHESIS_SDK_LOCAL_OUTPUT="+outputPath,
	)
	output, err := cmd.CombinedOutput()
	c.Assert(err, IsNil, Commentf("%s", output))
	data, err := os.ReadFile(outputPath)
	c.Assert(err, IsNil)

	decoder := json.NewDecoder(bytes.NewReader(data))
	encounters := 0
	for {
		var event struct {
			Assertion *struct {
				Message     string `json:"message"`
				Hit         bool   `json:"hit"`
				Condition   bool   `json:"condition"`
				DisplayType string `json:"display_type"`
				Details     struct {
					TaskID   string `json:"task-id"`
					ChangeID string `json:"change-id"`
					Kind     string `json:"kind"`
				} `json:"details"`
			} `json:"antithesis_assert"`
		}
		err := decoder.Decode(&event)
		if err == io.EOF {
			break
		}
		c.Assert(err, IsNil)
		if event.Assertion == nil || event.Assertion.Message != "snap abort accepted during in-flight task" || !event.Assertion.Hit {
			continue
		}
		encounters++
		c.Check(event.Assertion.Condition, Equals, true)
		c.Check(event.Assertion.DisplayType, Equals, "Reachable")
		c.Check(event.Assertion.Details.TaskID, Not(Equals), "")
		c.Check(event.Assertion.Details.ChangeID, Not(Equals), "")
		c.Check(event.Assertion.Details.Kind, Equals, "blocking")
	}
	c.Check(encounters, Equals, 1)
}

func (ts *taskRunnerSuite) TestTaskDispatchAssertion(c *C) {
	scenario := os.Getenv("SNAPD_TEST_TASK_DISPATCH")
	if scenario != "" {
		st := state.New(nil)
		runner := state.NewTaskRunner(st)
		defer runner.Stop()

		calls := make(chan string, 2)
		runner.AddHandler("target", func(*state.Task, *tomb.Tomb) error {
			calls <- "do"
			return nil
		}, func(*state.Task, *tomb.Tomb) error {
			calls <- "undo"
			return nil
		})

		blockerCalls := 0
		if scenario == "predicate-blocked" {
			runner.SetBlocked(func(*state.Task, []*state.Task) bool {
				blockerCalls++
				return true
			})
		}

		st.Lock()
		change := st.NewChange("install", "...")
		dependency := st.NewTask("unhandled", "dependency")
		task := st.NewTask("target", "target")
		change.AddTask(dependency)
		change.AddTask(task)

		expectDo := false
		expectUndo := false
		switch scenario {
		case "do", "do-blocked", "doing-replay":
			task.WaitFor(dependency)
			if scenario == "do" {
				dependency.SetStatus(state.DoneStatus)
			}
			if scenario == "doing-replay" {
				task.SetStatus(state.DoingStatus)
				expectDo = true
			}
			if scenario == "do" {
				expectDo = true
			}
		case "undo", "undo-blocked", "undoing-replay":
			dependency.WaitFor(task)
			if scenario == "undo" {
				dependency.SetStatus(state.DoneStatus)
			}
			task.SetStatus(state.UndoStatus)
			if scenario == "undoing-replay" {
				task.SetStatus(state.UndoingStatus)
			}
			expectUndo = scenario == "undo" || scenario == "undoing-replay"
		case "retry-not-due":
			dependency.SetStatus(state.DoneStatus)
			task.SetStatus(state.DoingStatus)
			now := time.Date(2026, time.November, 12, 0, 0, 0, 0, time.UTC)
			restoreTime := state.MockTime(now)
			defer restoreTime()
			task.At(now.Add(time.Hour))
		case "predicate-blocked":
			dependency.SetStatus(state.DoneStatus)
		default:
			c.Fatalf("unknown scenario %q", scenario)
		}
		st.Unlock()

		c.Assert(runner.Ensure(), IsNil)
		runner.Wait()
		callsCount := len(calls)
		if expectDo {
			c.Check(<-calls, Equals, "do")
		}
		if expectUndo {
			c.Check(<-calls, Equals, "undo")
		}
		expectedCalls := 0
		if expectDo {
			expectedCalls++
		}
		if expectUndo {
			expectedCalls++
		}
		c.Check(callsCount, Equals, expectedCalls)
		if scenario == "predicate-blocked" {
			c.Check(blockerCalls, Equals, 1)
		}
		return
	}

	for _, test := range []struct {
		scenario  string
		status    state.Status
		direction string
		hit       bool
	}{
		{scenario: "do", status: state.DoStatus, direction: "do", hit: true},
		{scenario: "do-blocked", status: state.DoStatus, direction: "do"},
		{scenario: "doing-replay", status: state.DoingStatus, direction: "do", hit: true},
		{scenario: "undo", status: state.UndoStatus, direction: "undo", hit: true},
		{scenario: "undo-blocked", status: state.UndoStatus, direction: "undo"},
		{scenario: "undoing-replay", status: state.UndoingStatus, direction: "undo", hit: true},
		{scenario: "retry-not-due", status: state.DoingStatus, direction: "do"},
		{scenario: "predicate-blocked", status: state.DoStatus, direction: "do"},
	} {
		outputPath := filepath.Join(c.MkDir(), "sdk.jsonl")
		cmd := exec.Command(os.Args[0], "-test.run=^TestState$", "-check.f=^taskRunnerSuite.TestTaskDispatchAssertion$")
		cmd.Env = append(os.Environ(),
			"SNAPD_TEST_TASK_DISPATCH="+test.scenario,
			"ANTITHESIS_SDK_LOCAL_OUTPUT="+outputPath,
		)
		output, err := cmd.CombinedOutput()
		c.Assert(err, IsNil, Commentf("%s: %s", test.scenario, output))
		data, err := os.ReadFile(outputPath)
		c.Assert(err, IsNil)

		decoder := json.NewDecoder(bytes.NewReader(data))
		encounters := 0
		for {
			var event struct {
				Assertion *struct {
					Message     string `json:"message"`
					Hit         bool   `json:"hit"`
					Condition   bool   `json:"condition"`
					DisplayType string `json:"display_type"`
					Details     struct {
						Status              string `json:"status"`
						Direction           string `json:"direction"`
						HasHandler          bool   `json:"has-handler"`
						HasActiveInvocation bool   `json:"has-active-invocation"`
						DependenciesBlocked bool   `json:"dependencies-blocked"`
						RetryDue            bool   `json:"retry-due"`
						PredicateBlocked    bool   `json:"predicate-blocked"`
					} `json:"details"`
				} `json:"antithesis_assert"`
			}
			err := decoder.Decode(&event)
			if err == io.EOF {
				break
			}
			c.Assert(err, IsNil, Commentf("%s", test.scenario))
			if event.Assertion == nil || event.Assertion.Message != "task dispatch respects runner scheduling gates" || !event.Assertion.Hit {
				continue
			}
			encounters++
			c.Check(event.Assertion.Condition, Equals, true, Commentf("%s", test.scenario))
			c.Check(event.Assertion.DisplayType, Equals, "Always")
			c.Check(event.Assertion.Details.Status, Equals, test.status.String())
			c.Check(event.Assertion.Details.Direction, Equals, test.direction)
			c.Check(event.Assertion.Details.HasHandler, Equals, true)
			c.Check(event.Assertion.Details.HasActiveInvocation, Equals, false)
			c.Check(event.Assertion.Details.DependenciesBlocked, Equals, false)
			c.Check(event.Assertion.Details.RetryDue, Equals, true)
			c.Check(event.Assertion.Details.PredicateBlocked, Equals, false)
		}
		expectedEncounters := 0
		if test.hit {
			expectedEncounters = 1
		}
		c.Check(encounters, Equals, expectedEncounters, Commentf("%s", test.scenario))
	}
}

func (ts *taskRunnerSuite) TestTaskCleanupAssertions(c *C) {
	scenario := os.Getenv("SNAPD_TEST_TASK_CLEANUP")
	if scenario != "" {
		st := state.New(nil)
		runner := state.NewTaskRunner(st)
		defer runner.Stop()

		cleanupCalls := 0
		runner.AddHandler("target", func(*state.Task, *tomb.Tomb) error { return nil }, nil)
		if scenario == "cleanup-success" || scenario == "cleanup-retry" || scenario == "change-not-ready" {
			runner.AddCleanup("target", func(*state.Task, *tomb.Tomb) error {
				cleanupCalls++
				if scenario == "cleanup-retry" && cleanupCalls == 1 {
					return errors.New("expected cleanup retry")
				}
				return nil
			})
		}

		st.Lock()
		change := st.NewChange("install", "...")
		task := st.NewTask("target", "target")
		change.AddTask(task)
		if scenario == "change-not-ready" {
			change.AddTask(st.NewTask("unhandled", "pending"))
		}
		task.SetStatus(state.DoneStatus)
		st.Unlock()

		c.Assert(runner.Ensure(), IsNil)
		runner.Wait()
		if scenario == "cleanup-retry" {
			st.Lock()
			c.Check(task.IsClean(), Equals, false)
			st.Unlock()
			c.Assert(runner.Ensure(), IsNil)
			runner.Wait()
			c.Check(cleanupCalls, Equals, 2)
		}
		st.Lock()
		c.Check(task.IsClean(), Equals, scenario != "change-not-ready")
		st.Unlock()
		return
	}

	for _, test := range []struct {
		scenario         string
		startEncounters  int
		commitEncounters int
	}{
		{scenario: "no-handler", commitEncounters: 1},
		{scenario: "cleanup-success", startEncounters: 1, commitEncounters: 1},
		{scenario: "cleanup-retry", startEncounters: 1, commitEncounters: 1},
		{scenario: "change-not-ready"},
	} {
		outputPath := filepath.Join(c.MkDir(), "sdk.jsonl")
		cmd := exec.Command(os.Args[0], "-test.run=^TestState$", "-check.f=^taskRunnerSuite.TestTaskCleanupAssertions$")
		cmd.Env = append(os.Environ(),
			"SNAPD_TEST_TASK_CLEANUP="+test.scenario,
			"ANTITHESIS_SDK_LOCAL_OUTPUT="+outputPath,
		)
		output, err := cmd.CombinedOutput()
		c.Assert(err, IsNil, Commentf("%s: %s", test.scenario, output))
		data, err := os.ReadFile(outputPath)
		c.Assert(err, IsNil)

		decoder := json.NewDecoder(bytes.NewReader(data))
		startEncounters, commitEncounters := 0, 0
		for {
			var event struct {
				Assertion *struct {
					Message     string `json:"message"`
					Hit         bool   `json:"hit"`
					Condition   bool   `json:"condition"`
					DisplayType string `json:"display_type"`
					Details     struct {
						ChangeID     string `json:"change-id"`
						TaskID       string `json:"task-id"`
						Outcome      string `json:"cleanup-outcome"`
						HandlerFound bool   `json:"cleanup-handler-present"`
					} `json:"details"`
				} `json:"antithesis_assert"`
			}
			err := decoder.Decode(&event)
			if err == io.EOF {
				break
			}
			c.Assert(err, IsNil, Commentf("%s", test.scenario))
			if event.Assertion == nil || !event.Assertion.Hit {
				continue
			}
			a := event.Assertion
			c.Check(a.Condition, Equals, true, Commentf("%s", test.scenario))
			c.Check(a.DisplayType, Equals, "AlwaysOrUnreachable")
			c.Check(a.Details.ChangeID, Not(Equals), "")
			c.Check(a.Details.TaskID, Not(Equals), "")
			switch a.Message {
			case "cleanup starts only after owning change is ready":
				startEncounters++
			case "runner clean commit follows eligible cleanup or no-handler path":
				commitEncounters++
				if test.scenario == "no-handler" {
					c.Check(a.Details.HandlerFound, Equals, false)
					c.Check(a.Details.Outcome, Equals, "no-handler")
				} else {
					c.Check(a.Details.HandlerFound, Equals, true)
					c.Check(a.Details.Outcome, Equals, "success")
				}
			}
		}
		c.Check(startEncounters, Equals, test.startEncounters, Commentf("%s", test.scenario))
		c.Check(commitEncounters, Equals, test.commitEncounters, Commentf("%s", test.scenario))
	}
}
