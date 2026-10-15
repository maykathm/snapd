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

package overlord_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"

	. "gopkg.in/check.v1"

	"github.com/snapcore/snapd/overlord"
	"github.com/snapcore/snapd/overlord/state"
)

type ensureManagerFunc func() error

func (f ensureManagerFunc) Ensure() error { return f() }

func (ses *stateEngineSuite) TestEnsureVisitationAssertion(c *C) {
	if scenario := os.Getenv("SNAPD_TEST_ENSURE_VISITATION"); scenario != "" {
		se := overlord.NewStateEngine(state.New(nil))
		calls := []string{}
		first := &fakeManager{name: "first", calls: &calls}
		last := &fakeManager{name: "last", calls: &calls}
		switch scenario {
		case "empty":
		case "errors":
			first.ensureError = errors.New("first error")
			last.ensureError = errors.New("last error")
			se.AddManager(first)
			se.AddManager(last)
		case "duplicate-slot":
			se.AddManager(first)
			se.AddManager(first)
		case "panic", "panic-then-success":
			se.AddManager(first)
			panicked := false
			se.AddManager(ensureManagerFunc(func() error {
				if !panicked {
					panicked = true
					panic("manager panic")
				}
				calls = append(calls, "ensure:recovered")
				return nil
			}))
			se.AddManager(last)
		default:
			se.AddManager(first)
			se.AddManager(last)
		}
		if scenario == "startup-error" {
			first.startupError = errors.New("startup error")
		}
		if scenario != "pre-start" {
			err := se.StartUp()
			if scenario == "startup-error" {
				c.Assert(err, ErrorMatches, "state startup errors: \\[startup error\\]")
			} else {
				c.Assert(err, IsNil)
			}
		}
		if scenario == "stopped" {
			se.Stop()
		}
		calls = nil
		switch scenario {
		case "pre-start":
			c.Check(se.Ensure(), ErrorMatches, "state engine skipped startup")
			c.Check(calls, HasLen, 0)
		case "stopped":
			c.Check(se.Ensure(), ErrorMatches, "state engine already stopped")
			c.Check(calls, HasLen, 0)
		case "panic", "panic-then-success":
			c.Check(func() { se.Ensure() }, PanicMatches, "manager panic")
			c.Check(calls, DeepEquals, []string{"ensure:first"})
			if scenario == "panic-then-success" {
				calls = nil
				c.Assert(se.Ensure(), IsNil)
				c.Check(calls, DeepEquals, []string{"ensure:first", "ensure:recovered", "ensure:last"})
			}
		case "errors":
			c.Check(se.Ensure(), ErrorMatches, "state ensure errors: \\[first error last error\\]")
			c.Check(calls, DeepEquals, []string{"ensure:first", "ensure:last"})
		case "duplicate-slot":
			c.Assert(se.Ensure(), IsNil)
			c.Check(calls, DeepEquals, []string{"ensure:first", "ensure:first"})
		case "empty":
			c.Assert(se.Ensure(), IsNil)
			c.Check(calls, HasLen, 0)
		default:
			c.Assert(se.Ensure(), IsNil)
			c.Check(calls, DeepEquals, []string{"ensure:first", "ensure:last"})
		}
		// Registration proves panic unwinding and normal returns release mgrLock.
		se.AddManager(&fakeManager{name: "added", calls: &calls})
		return
	}

	// SDK initialization and encounter deduplication require isolated processes.
	for _, scenario := range []string{"success", "errors", "duplicate-slot", "empty", "pre-start", "stopped", "panic", "panic-then-success", "startup-error"} {
		outputPath := filepath.Join(c.MkDir(), "sdk.jsonl")
		cmd := exec.Command(os.Args[0], "-test.run=^TestOverlord$", "-check.f=^stateEngineSuite.TestEnsureVisitationAssertion$")
		cmd.Env = append(os.Environ(), "SNAPD_TEST_ENSURE_VISITATION="+scenario, "ANTITHESIS_SDK_LOCAL_OUTPUT="+outputPath)
		output, err := cmd.CombinedOutput()
		c.Assert(err, IsNil, Commentf("%s: %s", scenario, output))
		data, err := os.ReadFile(outputPath)
		c.Assert(err, IsNil)
		decoder := json.NewDecoder(bytes.NewReader(data))
		encounters := 0
		for {
			var event struct {
				Assertion struct {
					Message     string `json:"message"`
					Hit         bool   `json:"hit"`
					Condition   bool   `json:"condition"`
					DisplayType string `json:"display_type"`
					Details     struct {
						Engine   string `json:"engine"`
						Pass     uint64 `json:"pass"`
						Expected int    `json:"expected"`
						Entered  []int  `json:"entered"`
						Returned []int  `json:"returned"`
						Errors   int    `json:"manager-errors"`
					} `json:"details"`
				} `json:"antithesis_assert"`
			}
			err := decoder.Decode(&event)
			if err == io.EOF {
				break
			}
			c.Assert(err, IsNil)
			a := event.Assertion
			if a.Message != "completed ensure pass visits every registered manager" || !a.Hit {
				continue
			}
			encounters++
			c.Check(a.Condition, Equals, true, Commentf("%s", scenario))
			c.Check(a.DisplayType, Equals, "Always")
			c.Check(a.Details.Engine, Matches, "0x[0-9a-f]+")
			pass := uint64(1)
			counts := []int{1, 1}
			if scenario == "empty" {
				counts = []int{}
			} else if scenario == "panic-then-success" {
				pass = 2
				counts = []int{1, 1, 1}
			}
			c.Check(a.Details.Pass, Equals, pass)
			c.Check(a.Details.Expected, Equals, len(counts))
			c.Check(a.Details.Entered, DeepEquals, counts)
			c.Check(a.Details.Returned, DeepEquals, counts)
			errorCount := 0
			if scenario == "errors" {
				errorCount = 2
			}
			c.Check(a.Details.Errors, Equals, errorCount)
		}
		expected := 1
		if scenario == "pre-start" || scenario == "stopped" || scenario == "panic" {
			expected = 0
		}
		c.Check(encounters, Equals, expected, Commentf("%s", scenario))
	}
}
