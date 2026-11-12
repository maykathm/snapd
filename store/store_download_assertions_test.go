//go:build !no_antithesis_sdk

package store_test

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"os/exec"
	"path/filepath"

	. "gopkg.in/check.v1"
)

func (s *storeDownloadSuite) TestDownloadBranchAssertions(c *C) {
	scenario := os.Getenv("SNAPD_TEST_DOWNLOAD_ASSERTION")
	if scenario != "" {
		switch scenario {
		case "resume":
			s.TestDownloadRangeRequestNon0Partial(c)
		case "valid-cache":
			s.TestDownloadCacheHitRecoveryFromPreexistingCorruptTarget(c)
		case "wrong-size-cache":
			s.TestDownloadCacheHitCorruptRedownloads(c)
		case "hash-retry":
			s.TestDownloadRetryHashErrorIsFullyRetried(c)
		case "completed-partial":
			s.TestResumeOfCompleted(c)
		default:
			c.Fatalf("unknown download assertion scenario %q", scenario)
		}
		return
	}

	for _, test := range []struct {
		scenario           string
		message            string
		expectedEncounters int
	}{
		{scenario: "resume", message: "snap download resumes from a nonzero offset", expectedEncounters: 1},
		{scenario: "valid-cache", message: "snap download recovered a valid cache entry", expectedEncounters: 1},
		{scenario: "wrong-size-cache", message: "snap download rejected a wrong-size cache entry", expectedEncounters: 1},
		{scenario: "hash-retry", message: "snap download retries after a hash mismatch", expectedEncounters: 1},
		{scenario: "completed-partial", message: "snap download resumes from a nonzero offset"},
	} {
		outputPath := filepath.Join(c.MkDir(), "sdk.jsonl")
		cmd := exec.Command(os.Args[0], "-test.run=^TestStore$", "-check.f=^storeDownloadSuite.TestDownloadBranchAssertions$")
		cmd.Env = append(os.Environ(),
			"SNAPD_TEST_DOWNLOAD_ASSERTION="+test.scenario,
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
				} `json:"antithesis_assert"`
			}
			err := decoder.Decode(&event)
			if err == io.EOF {
				break
			}
			c.Assert(err, IsNil)
			if event.Assertion == nil || event.Assertion.Message != test.message || !event.Assertion.Hit {
				continue
			}
			encounters++
			c.Check(event.Assertion.Condition, Equals, true)
			c.Check(event.Assertion.DisplayType, Equals, "Reachable")
		}
		c.Check(encounters, Equals, test.expectedEncounters)
	}
}
