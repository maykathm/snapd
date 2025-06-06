// -*- Mode: Go; indent-tabs-mode: t -*-

/*
 * Copyright (C) 2025 Canonical Ltd
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

package swfeats_test

import (
	"go/ast"
	"go/parser"
	"go/token"
	"path/filepath"
	"strings"
	"testing"

	. "gopkg.in/check.v1"

	"github.com/snapcore/snapd/overlord/swfeats"
	"github.com/snapcore/snapd/testutil"
)

func Test(t *testing.T) { TestingT(t) }

type swfeatsSuite struct {
	testutil.BaseTest
	ChangeReg *swfeats.ChangeKindRegistry
	EnsureReg *swfeats.EnsureRegistry
}

var _ = Suite(&swfeatsSuite{})

func (s *swfeatsSuite) SetupSuite(c *C) {
}

func (s *swfeatsSuite) SetUpTest(c *C) {
	s.ChangeReg = swfeats.NewChangeKindRegistry()
	s.EnsureReg = swfeats.AddRegistry()
}

func (s *swfeatsSuite) TestAddChange(c *C) {
	changeKind := s.ChangeReg.Add("my-change")
	c.Assert(changeKind, Equals, "my-change")
}

func (s *swfeatsSuite) TestKnownChangeKinds(c *C) {
	my_change1 := s.ChangeReg.Add("my-change1")
	c.Assert(my_change1, Equals, "my-change1")

	// Add the same change again to check that it isn't added
	// more than once
	my_change1 = s.ChangeReg.Add("my-change1")
	c.Assert(my_change1, Equals, "my-change1")
	my_change2 := s.ChangeReg.Add("my-change2")
	c.Assert(my_change2, Equals, "my-change2")
	changeKinds := s.ChangeReg.KnownChangeKinds()
	c.Assert(changeKinds, HasLen, 2)
	c.Assert(changeKinds, testutil.Contains, "my-change1")
	c.Assert(changeKinds, testutil.Contains, "my-change2")
}

func (s *swfeatsSuite) TestNewChangeTemplateKnown(c *C) {
	changeKind := s.ChangeReg.Add("my-change-%s")
	changeKind2 := s.ChangeReg.Add("my-change-%s")
	c.Assert(changeKind, Equals, changeKind2)
	kinds := s.ChangeReg.KnownChangeKinds()
	// Without possible values added, a templated change will generate
	// the template
	c.Assert(kinds, HasLen, 1)
	c.Assert(kinds, testutil.Contains, "my-change-%s")

	s.ChangeReg.AddVariants(changeKind, []string{"1", "2", "3"})
	kinds = s.ChangeReg.KnownChangeKinds()
	c.Assert(kinds, HasLen, 3)
	c.Assert(kinds, testutil.Contains, "my-change-1")
	c.Assert(kinds, testutil.Contains, "my-change-2")
	c.Assert(kinds, testutil.Contains, "my-change-3")
}

func (s *swfeatsSuite) TestAddEnsure(c *C) {
	c.Assert(s.EnsureReg.KnownEnsures(), HasLen, 0)
	s.EnsureReg.Add("MyManager", "myFunction")
	knownEnsures := s.EnsureReg.KnownEnsures()
	c.Assert(knownEnsures, HasLen, 1)
	c.Assert(knownEnsures, testutil.Contains, swfeats.EnsureEntry{Manager: "MyManager", Function: "myFunction"})
}

func (s *swfeatsSuite) TestDuplicateAdd(c *C) {
	s.EnsureReg.Add("MyManager", "myFunction1")
	s.EnsureReg.Add("MyManager", "myFunction1")
	s.EnsureReg.Add("MyManager", "myFunction2")
	s.EnsureReg.Add("MyManager", "myFunction2")
	knownEnsures := s.EnsureReg.KnownEnsures()
	c.Assert(knownEnsures, HasLen, 2)
	c.Assert(knownEnsures, testutil.Contains, swfeats.EnsureEntry{Manager: "MyManager", Function: "myFunction1"})
	c.Assert(knownEnsures, testutil.Contains, swfeats.EnsureEntry{Manager: "MyManager", Function: "myFunction2"})
}

func (s *swfeatsSuite) TestCheckRegistrations(c *C) {
	fset := token.NewFileSet()
	registeredVars := make(map[string]bool)
	wrapperFuncs := make(map[string]int)

	// files, err := filepath.Glob("../../overlord/ifacestate/hotplug.go")
	// files, err := filepath.Glob("../../overlord/hookstate/ctlcmd/helpers.go")
	// err := filepath.Walk("../../", func(path string, info os.FileInfo, err error) error {
	// 	if err != nil {
	// 		return err
	// 	}
	// 	if info.IsDir() {
	// 		matches, err := filepath.Glob(filepath.Join(path, "*.go"))
	// 		if err != nil {
	// 			return err
	// 		}
	// 		allFiles = append(allFiles, matches...)
	// 	}
	// 	return nil
	// })
	// if err != nil {
	// 	c.Fatalf("failed to walk directories: %v", err)
	// }
	// files = allFiles
	files, err := filepath.Glob("../../**/*.go")
	if err != nil {
		c.Fatalf("failed to list Go files: %v", err)
		// Exclude files ending with _test.go
	}
	filteredFiles := []string{}
	for _, file := range files {
		if filepath.Ext(file) == ".go" && !strings.HasSuffix(file, "_test.go") {
			filteredFiles = append(filteredFiles, file)
		}
	}
	files = filteredFiles
	for _, file := range files {
		f, err := parser.ParseFile(fset, file, nil, 0)
		if err != nil {
			c.Fatalf("failed to parse %s: %v", file, err)
		}
		ast.Inspect(f, func(n ast.Node) bool {
			// Registered vars from swfeats.ChangeReg.Add
			switch stmt := n.(type) {
			case *ast.ValueSpec:
				maybeAddRegistration(&registeredVars, stmt)
			case *ast.FuncDecl:
				// if the call to NewChange is actually a wrapper, add
				// that wrapper to the warpperFuncs
				maybeAddNewChangeWrapper(&wrapperFuncs, stmt)
			}
			return true
		})
	}
}

func resolveAlias(name string, aliases map[string]string, registeredVars map[string]bool) (string, bool) {
	visited := map[string]bool{}
	current := name
	for {
		if registeredVars[current] {
			return current, true
		}
		if visited[current] {
			// Cycle detected
			return current, false
		}
		visited[current] = true
		next, ok := aliases[current]
		if !ok {
			return current, false
		}
		current = next
	}
}

func maybeAddNewChangeWrapper(wrapperFuncs *map[string]int, stmt *ast.FuncDecl) {
	var kindParamIndex int = -1

	ast.Inspect(stmt.Body, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		sel, ok := call.Fun.(*ast.SelectorExpr)
		if !ok {
			return true
		}
		if sel.Sel.Name == "NewChange" {
			// if the function has arguments, check to see if
			// one of them is the same argument passed to the call
			// to NewChange
			if len(call.Args) > 0 {
				// The kind of change is the first parameter in NewChange
				switch arg := call.Args[0].(type) {
				case *ast.Ident:
					// check all function arguments to see if one of them
					// is passed to NewChange's first argument
					for i, param := range stmt.Type.Params.List {
						for _, name := range param.Names {
							if name.Name == arg.Name {
								kindParamIndex = i
								break
							}
						}
						if kindParamIndex != -1 {
							break
						}
					}
				}
			}
			if kindParamIndex != -1 {
				(*wrapperFuncs)[stmt.Name.Name] = kindParamIndex
			}
		}
		return true
	})
}

func maybeAddRegistration(registeredVars *map[string]bool, stmt *ast.ValueSpec) {
	for i, val := range stmt.Values {
		if call, ok := val.(*ast.CallExpr); ok {
			if addSel, ok := call.Fun.(*ast.SelectorExpr); ok && addSel.Sel.Name == "Add" {
				if changeRegSel, ok := addSel.X.(*ast.SelectorExpr); ok && changeRegSel.Sel.Name == "ChangeReg" {
					if swfeatsIdent, ok := changeRegSel.X.(*ast.Ident); ok && swfeatsIdent.Name == "swfeats" {
						(*registeredVars)[stmt.Names[i].Name] = true
					}
				}
			}
		}
	}
}

func (s *swfeatsSuite) TestNewChangeAndWrappersUseRegisteredChangeKind(c *C) {
	fset := token.NewFileSet()
	registeredVars := make(map[string]bool)
	wrapperFuncs := make(map[string]int) // funcName -> kindParamIndex

	// files, err := filepath.Glob("../../overlord/ifacestate/hotplug.go")
	files, err := filepath.Glob("../../overlord/hookstate/ctlcmd/helpers.go")
	// files, err := filepath.Glob("../../**/*.go")
	if err != nil {
		c.Fatalf("failed to list Go files: %v", err)
		// Exclude files ending with _test.go
	}
	filteredFiles := []string{}
	for _, file := range files {
		if filepath.Ext(file) == ".go" && !strings.HasSuffix(file, "_test.go") {
			filteredFiles = append(filteredFiles, file)
		}
	}
	files = filteredFiles
	for _, file := range files {
		f, err := parser.ParseFile(fset, file, nil, 0)
		if err != nil {
			c.Fatalf("failed to parse %s: %v", file, err)
		}

		// Step 1: Find registered vars and wrapper funcs
		ast.Inspect(f, func(n ast.Node) bool {
			// Registered vars from swfeats.ChangeReg.Add
			switch stmt := n.(type) {
			case *ast.ValueSpec:
				maybeAddRegistration(&registeredVars, stmt)
			case *ast.AssignStmt:
				for i, val := range stmt.Rhs {
					if call, ok := val.(*ast.CallExpr); ok {
						if sel, ok := call.Fun.(*ast.SelectorExpr); ok {
							if ident, ok := sel.X.(*ast.Ident); ok {
								if ident.Name == "swfeats.ChangeReg" && sel.Sel.Name == "Add" {
									if lhsIdent, ok := stmt.Lhs[i].(*ast.Ident); ok {
										registeredVars[lhsIdent.Name] = true
									}
								}
							}
						}
					}
				}
			case *ast.FuncDecl:
				// Check if this func calls NewChange
				var kindParamIndex int = -1

				ast.Inspect(stmt.Body, func(n ast.Node) bool {
					call, ok := n.(*ast.CallExpr)
					if !ok {
						return true
					}
					sel, ok := call.Fun.(*ast.SelectorExpr)
					if !ok {
						return true
					}
					if sel.Sel.Name == "NewChange" {
						// Find which argument corresponds to kind param
						if len(call.Args) > 0 {
							switch arg := call.Args[0].(type) {
							case *ast.Ident:
								// Try to find which param this corresponds to
								for i, param := range stmt.Type.Params.List {
									for _, name := range param.Names {
										if name.Name == arg.Name {
											kindParamIndex = i
											break
										}
									}
									if kindParamIndex != -1 {
										break
									}
								}
							}
						}
					}
					return true
				})

				if kindParamIndex != -1 {
					wrapperFuncs[stmt.Name.Name] = kindParamIndex
				}
			}
			return true
		})

		// Step 2: Check calls to NewChange directly
		ast.Inspect(f, func(n ast.Node) bool {
			call, ok := n.(*ast.CallExpr)
			if !ok {
				return true
			}
			sel, ok := call.Fun.(*ast.SelectorExpr)
			if ok && sel.Sel.Name == "NewChange" {
				if len(call.Args) == 0 {
					c.Errorf("call to NewChange with no arguments in %s", file)
					return true
				}
				switch arg := call.Args[0].(type) {
				case *ast.Ident:
					if !registeredVars[arg.Name] {
						c.Errorf("NewChange called with unregistered change kind variable %q in %s", arg.Name, file)
					}
				case *ast.BasicLit:
					if arg.Kind == token.STRING {
						c.Errorf("NewChange called with string literal %s instead of registered variable in %s", arg.Value, file)
					}
				case *ast.CallExpr:
					call2, _ := call.Args[0].(*ast.CallExpr)
					if len(call2.Args) == 0 {
						c.Errorf("call %q without arguments in file %s", call2.Fun, file)
					} else {
						found := false
						for _, call2Arg := range call2.Args {
							if ident, ok := call2Arg.(*ast.Ident); ok {
								if registeredVars[ident.Name] {
									found = true
								}
							}
						}
						if !found {
							c.Errorf("NewChange called with unregistered change kind variable %q in %s", call2.Fun, file)
						}
					}

				default:
					c.Errorf("NewChange called with unsupported first argument type in %s", file)
				}
			}
			return true
		})

		// Step 3: Check calls to wrapper functions
		ast.Inspect(f, func(n ast.Node) bool {
			call, ok := n.(*ast.CallExpr)
			if !ok {
				return true
			}
			funIdent, ok := call.Fun.(*ast.Ident)
			if !ok {
				return true
			}
			kindParamIndex, isWrapper := wrapperFuncs[funIdent.Name]
			if !isWrapper {
				return true
			}
			if len(call.Args) <= kindParamIndex {
				c.Errorf("call to wrapper function %s missing argument at kind param index %d in %s", funIdent.Name, kindParamIndex, file)
				return true
			}
			arg := call.Args[kindParamIndex]
			switch argIdent := arg.(type) {
			case *ast.Ident:
				if !registeredVars[argIdent.Name] {
					c.Errorf("wrapper function %s called with unregistered change kind variable %q in %s", funIdent.Name, argIdent.Name, file)
				}
			case *ast.BasicLit:
				if argIdent.Kind == token.STRING {
					c.Errorf("wrapper function %s called with string literal %s instead of registered variable in %s", funIdent.Name, argIdent.Value, file)
				}
			default:
				c.Errorf("wrapper function %s called with unsupported argument type for kind param in %s", funIdent.Name, file)
			}
			return true
		})
	}
}
