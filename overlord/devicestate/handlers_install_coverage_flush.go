//go:build go1.20 && withtestkeys
// +build go1.20,withtestkeys

/*
 * Copyright (C) 2024 Canonical Ltd
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

package devicestate

import (
	"os"
	"runtime/coverage"

	"github.com/snapcore/snapd/logger"
)

// doCoverageFlush performs the actual coverage counter flush on Go 1.20+
func doCoverageFlush() {
	goCoverDir := os.Getenv("GOCOVERDIR")
	if goCoverDir == "" {
		logger.Noticef("GOCOVERDIR is not set")
		return
	}

	logger.Noticef("flushing Go coverage counters to %s", goCoverDir)
	if err := coverage.WriteCountersDir(goCoverDir); err != nil {
		logger.Noticef("failed to write coverage counters: %v", err)
		return
	}
	logger.Noticef("successfully flushed coverage counters before system restart")
}
