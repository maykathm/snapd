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

package snapstate_test

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"os/exec"
	"strconv"

	. "gopkg.in/check.v1"

	"github.com/snapcore/snapd/overlord/snapstate"
	"github.com/snapcore/snapd/overlord/snapstate/sequence"
	"github.com/snapcore/snapd/overlord/snapstate/snapstatetest"
	"github.com/snapcore/snapd/overlord/state"
	"github.com/snapcore/snapd/snap"
)

func (s *snapStateSuite) TestSetCurrentInSequenceAssertion(c *C) {
	seq := snapstatetest.NewSequenceFromSnapSideInfos([]*snap.SideInfo{
		{Revision: snap.R(1)},
		{Revision: snap.R(2)},
		{Revision: snap.R(-1)},
	})
	tests := []struct {
		name      string
		snapst    *snapstate.SnapState
		encounter bool
		condition bool
	}{
		{"active", &snapstate.SnapState{SnapType: "app", Sequence: seq, Current: snap.R(2), Active: true}, true, true},
		{"disabled", &snapstate.SnapState{SnapType: "app", Sequence: seq, Current: snap.R(2)}, true, true},
		{"older-current", &snapstate.SnapState{SnapType: "app", Sequence: seq, Current: snap.R(1)}, true, true},
		{"local-revision", &snapstate.SnapState{SnapType: "app", Sequence: seq, Current: snap.R(-1)}, true, true},
		{"missing-current", &snapstate.SnapState{SnapType: "app", Sequence: seq, Current: snap.R(3)}, true, false},
		{"unset-current", &snapstate.SnapState{SnapType: "app", Sequence: seq}, true, false},
		{"unset-matches-zero", &snapstate.SnapState{SnapType: "app", Sequence: snapstatetest.NewSequenceFromSnapSideInfos([]*snap.SideInfo{{}})}, true, false},
		{"nil-revision", &snapstate.SnapState{SnapType: "app", Sequence: sequence.SnapSequence{Revisions: []*sequence.RevisionSideState{nil}}, Current: snap.R(1)}, true, false},
		{"nil", nil, false, false},
		{"empty-sequence", &snapstate.SnapState{SnapType: "app", Current: snap.R(1)}, false, false},
		{"unset-type", &snapstate.SnapState{Sequence: seq}, false, false},
		{"base", &snapstate.SnapState{SnapType: "base", Sequence: seq}, false, false},
		{"try-mode", &snapstate.SnapState{SnapType: "app", Sequence: seq, Flags: snapstate.Flags{TryMode: true}}, false, false},
	}

	// SDK output is configured at process startup and encounters are deduplicated.
	// Each case needs a fresh process to verify both the predicate and its gating.
	if index := os.Getenv("SNAPD_TEST_CURRENT_SEQUENCE_CASE"); index != "" {
		i, err := strconv.Atoi(index)
		c.Assert(err, IsNil)
		c.Assert(i >= 0 && i < len(tests), Equals, true)
		tc := tests[i]
		st := state.New(nil)
		st.Lock()
		defer st.Unlock()

		st.Set("snaps", map[string]string{"fixture_instance": "previous entry"})
		snapstate.Set(st, "fixture_instance", tc.snapst)
		var committed map[string]json.RawMessage
		c.Assert(st.Get("snaps", &committed), IsNil)
		if tc.snapst == nil || len(tc.snapst.Sequence.Revisions) == 0 {
			c.Check(committed, HasLen, 0)
		} else {
			expected, err := json.Marshal(tc.snapst)
			c.Assert(err, IsNil)
			c.Check(string(committed["fixture_instance"]), Equals, string(expected))
		}
		return
	}

	for i, tc := range tests {
		outputPath := c.MkDir() + "/sdk.jsonl"
		cmd := exec.Command(os.Args[0], "-test.run=^TestSnapManager$", "-check.f=^snapStateSuite.TestSetCurrentInSequenceAssertion$")
		cmd.Env = append(os.Environ(),
			"SNAPD_TEST_CURRENT_SEQUENCE_CASE="+strconv.Itoa(i),
			"ANTITHESIS_SDK_LOCAL_OUTPUT="+outputPath)
		output, err := cmd.CombinedOutput()
		c.Assert(err, IsNil, Commentf("%s: %s", tc.name, output))
		data, err := os.ReadFile(outputPath)
		c.Assert(err, IsNil, Commentf("%s", tc.name))

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
						Instance string        `json:"instance"`
						Current  snap.Revision `json:"current"`
						Active   bool          `json:"active"`
						Length   int           `json:"sequence-length"`
					} `json:"details"`
				} `json:"antithesis_assert"`
			}
			err := decoder.Decode(&event)
			if err == io.EOF {
				break
			}
			c.Assert(err, IsNil, Commentf("%s", tc.name))
			a := event.Assertion
			if a.Message != "committed app current belongs to its revision sequence" || !a.Hit {
				continue
			}
			encounters++
			c.Check(a.Condition, Equals, tc.condition, Commentf("%s", tc.name))
			c.Check(a.DisplayType, Equals, "Always")
			c.Assert(tc.snapst, NotNil)
			c.Check(a.Details.Instance, Equals, "fixture_instance")
			c.Check(a.Details.Current, Equals, tc.snapst.Current)
			c.Check(a.Details.Active, Equals, tc.snapst.Active)
			c.Check(a.Details.Length, Equals, len(tc.snapst.Sequence.Revisions))
		}
		expectedEncounters := 0
		if tc.encounter {
			expectedEncounters = 1
		}
		c.Check(encounters, Equals, expectedEncounters, Commentf("%s", tc.name))
	}
}
